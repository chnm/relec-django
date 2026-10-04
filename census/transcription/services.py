"""Application services for creating immutable transcription runs."""

from datetime import timedelta

from django.conf import settings
from django.db import connection, models, transaction
from django.utils import timezone
from simple_history.utils import bulk_create_with_history

from census.models import TranscriptionBatch, TranscriptionJob, TranscriptionRun

from .contracts import load_contract
from .usage import PricingConfigurationError, pricing_snapshot_for_model

#: How many lease periods an active batch may go without a heartbeat before the
#: worker holding it is treated as stuck rather than merely slow.
STALE_LEASE_PERIODS = 2
# Serialize launch eligibility checks so two reviewers cannot queue the same
# schedule concurrently in separate runs.
LAUNCH_ADVISORY_LOCK_ID = 6401927
SONNET_5_MODEL = "claude-sonnet-5"


class LaunchError(ValueError):
    pass


ACTIVE_JOB_STATES = (
    TranscriptionJob.State.QUEUED,
    TranscriptionJob.State.PREPARING,
    TranscriptionJob.State.SUBMITTED,
    TranscriptionJob.State.NEEDS_RECOVERY,
)


def inference_config_for_model(model):
    """Return the request behavior that must be frozen for this model."""
    if model == SONNET_5_MODEL:
        # Sonnet 5 otherwise enables high-effort adaptive thinking by default,
        # and thinking shares max_tokens with the structured response. Disabling
        # thinking entirely (the previous approach) degraded reading quality and
        # produced near-empty candidates on legible schedules; low effort keeps
        # thinking brief enough that the JSON still fits within the budget.
        return {"thinking": {"type": "adaptive"}, "output_effort": "low"}
    return {}


def eligible_transcription_schedules(queryset):
    """Return selected schedules that can safely start another attempt."""
    active_job = TranscriptionJob.objects.filter(
        census_schedule_id=models.OuterRef("pk"),
        state__in=ACTIVE_JOB_STATES,
    )
    return (
        queryset.exclude(original_image="")
        .exclude(original_image__isnull=True)
        .annotate(_has_active_transcription_job=models.Exists(active_job))
        .filter(_has_active_transcription_job=False)
    )


def transcription_selection_summary(queryset):
    """Return mutually exclusive counts for the run confirmation screen."""
    selected_count = queryset.count()
    missing_image_count = queryset.filter(
        models.Q(original_image="") | models.Q(original_image__isnull=True)
    ).count()
    eligible_count = eligible_transcription_schedules(queryset).count()
    return {
        "selected_count": selected_count,
        "eligible_count": eligible_count,
        "missing_image_count": missing_image_count,
        "active_work_count": selected_count - missing_image_count - eligible_count,
    }


def worker_status(now=None):
    """Summarize worker health from batch evidence the web tier can observe.

    The web process cannot see the worker directly: they share only the
    database, and the worker writes to it only while it holds work. A quiet
    database therefore means "nothing queued", never "not running", and this
    function is careful not to claim otherwise. The one honest liveness signal
    is a batch that is still active while its heartbeat has lapsed well past
    the lease window, which is what a hung worker looks like from here.
    """
    now = now or timezone.now()
    stale_before = now - (
        timedelta(seconds=settings.CLAUDE_TRANSCRIPTION_LEASE_SECONDS)
        * STALE_LEASE_PERIODS
    )
    batches = TranscriptionBatch.objects.all()
    active = (
        batches.filter(state__in=TranscriptionBatch.ACTIVE_STATES)
        .order_by(models.F("heartbeat_at").desc(nulls_last=True), "-pk")
        .first()
    )
    unrecovered = batches.filter(state=TranscriptionBatch.State.NEEDS_RECOVERY).count()
    last_activity = batches.aggregate(latest=models.Max("heartbeat_at"))["latest"]

    if active is not None and (
        active.heartbeat_at is None or active.heartbeat_at < stale_before
    ):
        return {
            "tone": "alert",
            "label": "Stalled",
            "detail": (
                f"Batch {active.pk} is {active.get_state_display().lower()} but "
                "has not renewed its lease. Check the worker container."
            ),
            "last_activity": active.heartbeat_at,
        }
    if unrecovered:
        noun = "batch" if unrecovered == 1 else "batches"
        verb = "requires" if unrecovered == 1 else "require"
        return {
            "tone": "warn",
            "label": "Needs recovery",
            "detail": f"{unrecovered} {noun} {verb} manual recovery.",
            "last_activity": last_activity,
        }
    if active is not None:
        return {
            "tone": "ok",
            "label": "Working",
            "detail": f"Batch {active.pk} is {active.get_state_display().lower()}.",
            "last_activity": active.heartbeat_at,
        }
    return {
        "tone": "idle",
        "label": "Idle",
        "detail": (
            "No active batch. The worker writes only while it holds work, so "
            "this cannot confirm the process is running."
        ),
        "last_activity": last_activity,
    }


@transaction.atomic
def launch_transcription_run(
    *,
    queryset,
    key,
    model,
    pilot_size=None,
    confirmed_job_count=None,
    user=None,
):
    """Freeze one campaign and queue every eligible schedule, or a pilot."""
    # Deliberately does not check ANTHROPIC_API_KEY. Only the worker talks to
    # the provider, so the key belongs in the worker's environment alone and
    # the web process must never require it.
    if not settings.CLAUDE_TRANSCRIPTION_ENABLED:
        raise LaunchError("Claude transcription is disabled by configuration.")
    if model not in settings.CLAUDE_TRANSCRIPTION_MODELS:
        raise LaunchError("The selected Claude model is not allowed.")
    if pilot_size is not None and (
        pilot_size < 1 or pilot_size > settings.CLAUDE_TRANSCRIPTION_MAX_RUN_JOBS
    ):
        raise LaunchError(
            "Pilot size must be between 1 and "
            f"{settings.CLAUDE_TRANSCRIPTION_MAX_RUN_JOBS}."
        )
    try:
        pricing_snapshot = pricing_snapshot_for_model(
            settings.CLAUDE_TRANSCRIPTION_PRICING, model
        )
    except PricingConfigurationError as exc:
        raise LaunchError(str(exc)) from exc

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_advisory_xact_lock(%s)",
            [LAUNCH_ADVISORY_LOCK_ID],
        )

    selection_count = queryset.count()
    # Admin querysets eagerly join nullable assignment and location relations for
    # list display. PostgreSQL cannot apply an unrestricted FOR UPDATE to the
    # nullable side of those outer joins, and launch eligibility needs to lock only
    # CensusSchedule rows in any case.
    locked_schedules = queryset.select_related(None).select_for_update(of=("self",))
    eligible = eligible_transcription_schedules(locked_schedules).order_by("pk")
    eligible_count = eligible.count()
    planned_count = min(eligible_count, pilot_size) if pilot_size else eligible_count
    if planned_count > settings.CLAUDE_TRANSCRIPTION_MAX_RUN_JOBS:
        raise LaunchError(
            f"This run would queue {planned_count:,} jobs, above the emergency "
            f"ceiling of {settings.CLAUDE_TRANSCRIPTION_MAX_RUN_JOBS:,}."
        )
    if (
        planned_count >= settings.CLAUDE_TRANSCRIPTION_LARGE_RUN_THRESHOLD
        and confirmed_job_count != planned_count
    ):
        raise LaunchError(
            f"Confirm the exact planned job count ({planned_count:,}) for this "
            "large run."
        )

    schedules = list(eligible[:planned_count])
    if not schedules:
        raise LaunchError(
            "None of the selected schedules is ready. Each needs an original "
            "image and no active Claude job."
        )

    contract = load_contract()
    metadata = {
        "provider": "anthropic",
        "orchestration": "messages_batch_api",
        "application_revision": settings.APPLICATION_REVISION or None,
        "model": model,
        "max_tokens": settings.CLAUDE_TRANSCRIPTION_MAX_TOKENS,
        "contract_version": contract["version"],
        "prompt": contract["prompt"],
        "prompt_sha256": contract["prompt_sha256"],
        "schema": contract["schema"],
        "schema_sha256": contract["schema_sha256"],
        "transport_schema": contract["transport_schema"],
        "transport_schema_sha256": contract["transport_schema_sha256"],
        "pricing_snapshot": pricing_snapshot,
        "selection_count": selection_count,
        "eligible_count": eligible_count,
        "pilot_size": pilot_size,
        "schedule_count": len(schedules),
        "estimated_batch_count": (
            len(schedules) + settings.CLAUDE_TRANSCRIPTION_BATCH_SIZE - 1
        )
        // settings.CLAUDE_TRANSCRIPTION_BATCH_SIZE,
        "schedule_ids": [schedule.pk for schedule in schedules],
        "launched_at": timezone.now().isoformat(),
        "launched_by": user.get_username() if user and user.is_authenticated else None,
    }
    metadata.update(inference_config_for_model(model))
    run = TranscriptionRun.objects.create(key=key, kind="agent", metadata=metadata)
    bulk_create_with_history(
        [TranscriptionJob(census_schedule=schedule, run=run) for schedule in schedules],
        TranscriptionJob,
        batch_size=1000,
    )
    return run
