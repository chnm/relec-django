"""Application services for creating immutable transcription runs."""

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from census.models import TranscriptionJob, TranscriptionRun

from .contracts import load_contract


class LaunchError(ValueError):
    pass


@transaction.atomic
def launch_transcription_run(*, queryset, key, model, limit, user=None):
    """Freeze provenance and queue one job per selected schedule."""
    if not settings.CLAUDE_TRANSCRIPTION_ENABLED:
        raise LaunchError("Claude transcription is disabled by configuration.")
    if not settings.ANTHROPIC_API_KEY:
        raise LaunchError("ANTHROPIC_API_KEY is not configured.")
    if not settings.APPLICATION_REVISION:
        raise LaunchError("APPLICATION_REVISION is not configured.")
    if model not in settings.CLAUDE_TRANSCRIPTION_MODELS:
        raise LaunchError("The selected Claude model is not allowed.")
    if limit < 1 or limit > settings.CLAUDE_TRANSCRIPTION_MAX_RUN_LIMIT:
        raise LaunchError(
            f"Limit must be between 1 and {settings.CLAUDE_TRANSCRIPTION_MAX_RUN_LIMIT}."
        )

    schedules = list(
        queryset.select_related("county__state", "schedule_denomination")
        .exclude(original_image="")
        .exclude(original_image__isnull=True)
        .order_by("pk")[:limit]
    )
    if not schedules:
        raise LaunchError("None of the selected schedules has an original image.")

    contract = load_contract()
    metadata = {
        "provider": "anthropic",
        "orchestration": "messages_batch_api",
        "application_revision": settings.APPLICATION_REVISION,
        "model": model,
        "max_tokens": settings.CLAUDE_TRANSCRIPTION_MAX_TOKENS,
        "contract_version": contract["version"],
        "prompt": contract["prompt"],
        "prompt_sha256": contract["prompt_sha256"],
        "schema": contract["schema"],
        "schema_sha256": contract["schema_sha256"],
        "transport_schema": contract["transport_schema"],
        "transport_schema_sha256": contract["transport_schema_sha256"],
        "pricing_snapshot": settings.CLAUDE_TRANSCRIPTION_PRICING,
        "requested_limit": limit,
        "schedule_count": len(schedules),
        "schedule_ids": [schedule.pk for schedule in schedules],
        "launched_at": timezone.now().isoformat(),
        "launched_by": user.get_username() if user and user.is_authenticated else None,
    }
    run = TranscriptionRun.objects.create(key=key, kind="agent", metadata=metadata)
    for schedule in schedules:
        TranscriptionJob.objects.create(census_schedule=schedule, run=run)
    return run
