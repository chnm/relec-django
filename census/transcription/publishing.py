"""Background publishing of one agent run over many schedules (issue #168).

A reviewer starts a publication; the worker previews (classifies) every item,
the reviewer confirms the counts, and the worker applies. Design:
docs/superpowers/specs/2026-10-07-background-run-publishing-design.md
"""

import logging

from django.db import transaction
from django.utils import timezone

from census.models import (
    Clergy,
    Membership,
    ReligiousBody,
    RunPublication,
    RunPublicationItem,
    ScheduleReconciliation,
)
from census.transcription.reconciliation import (
    ReconciliationError,
    apply_reconciliation,
    approve_schedule,
    build_reconciliation_preview,
    canonical_unchanged_since,
    schedule_graph_queryset,
)

logger = logging.getLogger(__name__)

#: Items handled per worker iteration; keeps each well inside the liveness window.
CHUNK_SIZE = 200

Case = RunPublicationItem.Case
Outcome = RunPublicationItem.Outcome
State = RunPublication.State

AGENT_APPLIED_OUTCOMES = (
    ScheduleReconciliation.Outcome.PROMOTED_CANDIDATE,
    ScheduleReconciliation.Outcome.MIXED,
)


def already_reconciled_against(schedule, source):
    """True when a standing reconciliation already decided on this run.

    That is the newest unreversed reconciliation, if it used this output in any
    way (accepted, partially incorporated, or rejected) or came after it. A
    person's choice there must not be overwritten by publishing.
    """
    latest = schedule.reconciliations.filter(reverses__isnull=True).first()
    return bool(
        latest
        and not latest.reversals.exists()
        and (
            latest.applied_at >= source.created_at
            or latest.sources.filter(transcription=source).exists()
        )
    )


def publish_case(schedule, run):
    """Classify one schedule for publishing ``run``. Returns ``(case, source)``.

    Agent output wins unless a person already decided about it: a standing
    reconciliation that used this run or came after it, or an edit to agent data
    applied by an earlier reconciliation.
    """
    source = (
        schedule.transcriptions.filter(run=run).order_by("-created_at", "-pk").first()
    )
    if source is None:
        return Case.NO_OUTPUT, None
    if already_reconciled_against(schedule, source):
        return Case.RECONCILED, source
    agent_applied = schedule.reconciliations.filter(
        reverses__isnull=True,
        reversals__isnull=True,
        outcome__in=AGENT_APPLIED_OUTCOMES,
    ).first()
    if agent_applied and not canonical_unchanged_since(
        schedule_graph_queryset().get(pk=schedule.pk), agent_applied
    ):
        return Case.EDITED, source
    return Case.PROMOTE, source


def saved_by_person_since(schedule, moment):
    """Whether a person saved the schedule or its rows after ``moment``.

    Only feeds the overwrite warning: form edits made before any reconciliation
    are not protected, but reviewers should see how many there are.
    """
    # ponytail: any human save counts, including status-only saves; diff the
    # history rows if the warning proves too noisy.
    recent = {"history_date__gt": moment, "history_user__isnull": False}
    return (
        schedule.history.filter(**recent).exists()
        or ReligiousBody.history.filter(census_record_id=schedule.pk, **recent).exists()
        or Membership.history.filter(census_record_id=schedule.pk, **recent).exists()
        or Clergy.history.filter(census_schedule_id=schedule.pk, **recent).exists()
    )


@transaction.atomic
def start_publication(*, run, schedule_ids, user):
    publication = RunPublication.objects.create(run=run, requested_by=user)
    RunPublicationItem.objects.bulk_create(
        (
            RunPublicationItem(publication=publication, census_schedule_id=pk)
            for pk in schedule_ids
        ),
        batch_size=1000,
    )
    return publication


def confirm_publication(publication, *, user, notes=""):
    """Move a previewed publication to publishing. Returns whether it moved."""
    return bool(
        RunPublication.objects.filter(pk=publication.pk, state=State.READY).update(
            state=State.PUBLISHING,
            confirmed_by=user,
            confirmed_at=timezone.now(),
            notes=notes.strip(),
        )
    )


def cancel_publication(publication):
    """Stop a publication at the next chunk boundary. Returns whether it stopped."""
    return bool(
        RunPublication.objects.filter(
            pk=publication.pk,
            state__in=[State.PREVIEWING, State.READY, State.PUBLISHING],
        ).update(state=State.CANCELED, finished_at=timezone.now())
    )


class PublicationWorker:
    """Advances the oldest active publication by one chunk per call.

    Assumes a single worker process (production runs one replica). Re-running an
    item after a crash is safe: classification is idempotent, and a re-applied
    promotion finds its own reconciliation and keeps the data.
    """

    def run_once(self):
        publication = (
            RunPublication.objects.filter(
                state__in=[State.PREVIEWING, State.PUBLISHING]
            )
            .select_related("run", "confirmed_by")
            .order_by("created_at", "pk")
            .first()
        )
        if publication is None:
            return False
        if publication.state == State.PREVIEWING:
            self._preview_chunk(publication)
        else:
            self._publish_chunk(publication)
        return True

    def _preview_chunk(self, publication):
        items = list(
            publication.items.filter(case="", outcome="").select_related(
                "census_schedule"
            )[:CHUNK_SIZE]
        )
        if not items:
            RunPublication.objects.filter(
                pk=publication.pk, state=State.PREVIEWING
            ).update(state=State.READY)
            return
        for item in items:
            try:
                item.case, source = publish_case(item.census_schedule, publication.run)
                item.overwrite_warning = (
                    item.case == Case.PROMOTE
                    and saved_by_person_since(item.census_schedule, source.created_at)
                )
            except Exception as exc:
                logger.exception("Could not preview publication item %s", item.pk)
                item.outcome, item.detail = Outcome.FAILED, f"Preview failed: {exc}"
        RunPublicationItem.objects.bulk_update(
            items, ["case", "overwrite_warning", "outcome", "detail"]
        )

    def _publish_chunk(self, publication):
        items = list(
            publication.items.filter(outcome="").select_related("census_schedule")[
                :CHUNK_SIZE
            ]
        )
        if not items:
            RunPublication.objects.filter(
                pk=publication.pk, state=State.PUBLISHING
            ).update(state=State.COMPLETED, finished_at=timezone.now())
            return
        for item in items:
            try:
                self._publish_item(publication, item)
            except Exception as exc:
                logger.exception("Could not publish publication item %s", item.pk)
                item.outcome, item.detail = Outcome.FAILED, str(exc)
            item.save(update_fields=["case", "outcome", "detail"])

    @staticmethod
    def _publish_item(publication, item):
        schedule = item.census_schedule
        # Re-classify: the schedule may have changed since the preview.
        item.case, source = publish_case(schedule, publication.run)
        if item.case == Case.NO_OUTPUT:
            item.outcome, item.detail = Outcome.SKIPPED, "No output from this run"
        elif item.case in (Case.RECONCILED, Case.EDITED):
            if schedule.transcription_status == "completed":
                approve_schedule(schedule, publication.confirmed_by)
                item.outcome = Outcome.APPROVED
            else:
                item.outcome = Outcome.KEPT
                if schedule.transcription_status != "approved":
                    item.detail = "Not ready for review"
        else:
            notes = f"Published run {publication.run.key}."
            if publication.notes:
                notes = f"{notes}\n{publication.notes}"
            try:
                preview = build_reconciliation_preview(schedule, source)
                apply_reconciliation(
                    schedule_id=schedule.pk,
                    reviewer=publication.confirmed_by,
                    expected_fingerprint=preview["before_fingerprint"],
                    comparison_transcription_id=source.pk,
                    notes=notes,
                )
            except ReconciliationError as exc:
                item.outcome, item.detail = Outcome.SKIPPED, str(exc)
            else:
                item.outcome = Outcome.PUBLISHED
