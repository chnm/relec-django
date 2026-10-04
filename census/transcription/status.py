"""Shared schedule-level status for the Claude candidate workflow."""

from django.db import models

from census.models import ReconciliationSource, ScheduleTranscription, TranscriptionJob

AI_STATUS_LABELS = {
    "not_queued": "Not queued",
    "queued": "Queued",
    "processing": "Processing",
    "transcribed": "AI transcribed",
    "reviewed": "AI reviewed",
    "failed": "Failed",
    "needs_recovery": "Needs recovery",
}


def with_ai_status(queryset):
    """Annotate the mutually exclusive latest AI workflow state."""
    latest_job = TranscriptionJob.objects.filter(
        census_schedule_id=models.OuterRef("pk"),
        run__kind="agent",
    ).order_by("-queued_at", "-pk")
    agent_candidate = ScheduleTranscription.objects.filter(
        census_schedule_id=models.OuterRef("pk"),
        run__kind="agent",
    )
    pending_agent_candidate = agent_candidate.exclude(
        reconciliation_sources__disposition__in=(
            ReconciliationSource.Disposition.ACCEPTED,
            ReconciliationSource.Disposition.INCORPORATED,
            ReconciliationSource.Disposition.REJECTED,
            ReconciliationSource.Disposition.SUPERSEDED,
        )
    )
    return queryset.annotate(
        _latest_ai_job_state=models.Subquery(latest_job.values("state")[:1]),
        _has_ai_candidate=models.Exists(agent_candidate),
        _has_pending_ai_candidate=models.Exists(pending_agent_candidate),
    ).annotate(
        _ai_status=models.Case(
            models.When(
                _latest_ai_job_state__in=[
                    TranscriptionJob.State.QUEUED,
                    TranscriptionJob.State.PREPARING,
                ],
                then=models.Value("queued"),
            ),
            models.When(
                _latest_ai_job_state=TranscriptionJob.State.SUBMITTED,
                then=models.Value("processing"),
            ),
            models.When(
                _latest_ai_job_state=TranscriptionJob.State.SUCCEEDED,
                _has_pending_ai_candidate=True,
                then=models.Value("transcribed"),
            ),
            models.When(
                _latest_ai_job_state__in=[
                    TranscriptionJob.State.FAILED,
                    TranscriptionJob.State.EXPIRED,
                    TranscriptionJob.State.CANCELED,
                    TranscriptionJob.State.INVALID,
                ],
                then=models.Value("failed"),
            ),
            models.When(
                _latest_ai_job_state=TranscriptionJob.State.NEEDS_RECOVERY,
                then=models.Value("needs_recovery"),
            ),
            models.When(
                _has_pending_ai_candidate=True,
                then=models.Value("transcribed"),
            ),
            models.When(_has_ai_candidate=True, then=models.Value("reviewed")),
            default=models.Value("not_queued"),
            output_field=models.CharField(max_length=20),
        )
    )
