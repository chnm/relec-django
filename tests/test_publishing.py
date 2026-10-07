from unittest.mock import patch

import pytest
from django.contrib import admin
from django.core.management import call_command
from django.test import RequestFactory, override_settings

from census.admin import (
    CensusScheduleAdmin,
    RunPublicationAdmin,
    publish_transcription_run,
)
from census.models import CensusSchedule, RunPublication, RunPublicationItem
from census.transcription.publishing import (
    CHUNK_SIZE,
    PublicationWorker,
    confirm_publication,
    start_publication,
)
from census.transcription.reconciliation import serialize_canonical
from census.transcription.worker import ClaudeTranscriptionWorker
from tests.test_reconciliation import (  # noqa: F401 (reviewer is a fixture)
    agent_candidate,
    agent_source,
    bulk_action_request,
    canonical_schedule,
    promote,
    reviewer,
)

State = RunPublication.State
Case = RunPublicationItem.Case
Outcome = RunPublicationItem.Outcome


def drain():
    worker = PublicationWorker()
    while worker.run_once():
        pass


def publish(reviewer, schedules, run):
    publication = start_publication(
        run=run, schedule_ids=[s.pk for s in schedules], user=reviewer
    )
    drain()
    publication.refresh_from_db()
    assert publication.state == State.READY
    assert confirm_publication(publication, user=reviewer, notes="Bulk review.")
    drain()
    publication.refresh_from_db()
    assert publication.state == State.COMPLETED
    return publication


def outcome(publication, schedule):
    return publication.items.get(census_schedule=schedule)


@pytest.mark.django_db
def test_publish_promotes_the_chosen_run_and_skips_schedules_without_output(
    reviewer,
):
    schedule = canonical_schedule()
    chosen = agent_source(schedule)
    agent_source(
        schedule,
        agent_candidate(
            respondent={
                "name": "Newer run reading",
                "title": None,
                "po_address": None,
                "date_signed": None,
            }
        ),
    )
    uncovered = canonical_schedule()

    publication = publish(reviewer, [schedule, uncovered], chosen.run)

    schedule.refresh_from_db()
    assert schedule.respondent_name == "Agent Respondent"
    assert schedule.transcription_status == "approved"
    event = schedule.reconciliations.get()
    assert event.sources.filter(transcription=chosen).exists()
    assert "Bulk review." in event.notes
    assert event.reviewer == reviewer
    assert outcome(publication, schedule).outcome == Outcome.PUBLISHED
    assert outcome(publication, uncovered).outcome == Outcome.SKIPPED
    assert not uncovered.reconciliations.exists()


@pytest.mark.django_db
def test_publish_keeps_a_persons_reconciliation_choices(reviewer):
    from census.transcription.reconciliation import (
        apply_reconciliation,
        build_reconciliation_preview,
    )

    schedule = canonical_schedule()
    source = agent_source(schedule)
    # A transcriber kept the human data over the agent output and submitted it.
    apply_reconciliation(
        schedule_id=schedule.pk,
        reviewer=reviewer,
        expected_fingerprint=build_reconciliation_preview(schedule)[
            "before_fingerprint"
        ],
        baseline_transcription_id=source.pk,
        approve=False,
        allow_removals=False,
    )
    before = serialize_canonical(schedule)

    publication = publish(reviewer, [schedule], source.run)

    schedule.refresh_from_db()
    assert serialize_canonical(schedule) == before
    assert schedule.transcription_status == "approved"
    assert schedule.reconciliations.count() == 1
    item = outcome(publication, schedule)
    assert (item.case, item.outcome) == (Case.RECONCILED, Outcome.APPROVED)


@pytest.mark.django_db
def test_publishing_the_same_run_twice_keeps_the_first_result(reviewer):
    schedule = canonical_schedule()
    source = agent_source(schedule)
    publish(reviewer, [schedule], source.run)

    publication = publish(reviewer, [schedule], source.run)

    assert schedule.reconciliations.count() == 1
    item = outcome(publication, schedule)
    assert (item.case, item.outcome) == (Case.RECONCILED, Outcome.KEPT)


@pytest.mark.django_db
def test_publish_keeps_a_persons_edit_to_an_earlier_agent_version(reviewer):
    schedule = canonical_schedule()
    promote(reviewer, schedule, agent_source(schedule))
    schedule.refresh_from_db()
    schedule.respondent_name = "Corrected by a person"
    schedule.transcription_status = "completed"
    schedule.save()
    newer = agent_source(schedule)

    publication = publish(reviewer, [schedule], newer.run)

    schedule.refresh_from_db()
    assert schedule.respondent_name == "Corrected by a person"
    assert schedule.transcription_status == "approved"
    assert (outcome(publication, schedule).case) == Case.EDITED


@pytest.mark.django_db
def test_publish_leaves_kept_work_alone_when_not_ready_for_review(reviewer):
    schedule = canonical_schedule()
    promote(reviewer, schedule, agent_source(schedule))
    schedule.refresh_from_db()
    schedule.respondent_name = "Still being corrected"
    schedule.transcription_status = "in_progress"
    schedule.save()
    newer = agent_source(schedule)

    publication = publish(reviewer, [schedule], newer.run)

    schedule.refresh_from_db()
    assert schedule.respondent_name == "Still being corrected"
    assert schedule.transcription_status == "in_progress"
    item = outcome(publication, schedule)
    assert (item.outcome, item.detail) == (Outcome.KEPT, "Not ready for review")


@pytest.mark.django_db
def test_preview_flags_form_edits_and_changes_nothing(reviewer):
    schedule = canonical_schedule()
    source = agent_source(schedule)
    schedule.respondent_name = "Typed in the form"
    schedule._history_user = reviewer
    schedule.save()
    before = serialize_canonical(schedule)

    publication = start_publication(
        run=source.run, schedule_ids=[schedule.pk], user=reviewer
    )
    drain()

    publication.refresh_from_db()
    item = outcome(publication, schedule)
    assert publication.state == State.READY
    assert (item.case, item.overwrite_warning, item.outcome) == (
        Case.PROMOTE,
        True,
        "",
    )
    assert serialize_canonical(schedule) == before


@pytest.mark.django_db
def test_worker_handles_one_chunk_per_iteration(reviewer):
    source = agent_source(canonical_schedule())
    schedules = [source.census_schedule] + [
        canonical_schedule() for _ in range(CHUNK_SIZE)
    ]
    publication = start_publication(
        run=source.run, schedule_ids=[s.pk for s in schedules], user=reviewer
    )

    assert PublicationWorker().run_once()
    assert publication.items.exclude(case="").count() == CHUNK_SIZE
    assert PublicationWorker().run_once()
    assert publication.items.filter(case="").count() == 0
    assert PublicationWorker().run_once()  # marks the preview ready
    publication.refresh_from_db()
    assert publication.state == State.READY


@pytest.mark.django_db
def test_canceled_publication_stops(reviewer):
    schedule = canonical_schedule()
    source = agent_source(schedule)
    publication = start_publication(
        run=source.run, schedule_ids=[schedule.pk], user=reviewer
    )
    model_admin = RunPublicationAdmin(RunPublication, admin.site)

    model_admin.change_view(
        bulk_action_request(reviewer, cancel="1"), str(publication.pk)
    )

    assert not PublicationWorker().run_once()
    publication.refresh_from_db()
    assert publication.state == State.CANCELED
    assert not schedule.reconciliations.exists()


@pytest.mark.django_db
def test_action_starts_a_preview_and_status_page_confirms_it(reviewer):
    schedule = canonical_schedule()
    source = agent_source(schedule)
    queryset = CensusSchedule.objects.filter(pk=schedule.pk)
    model_admin = CensusScheduleAdmin(CensusSchedule, admin.site)

    start_page = publish_transcription_run(
        model_admin,
        bulk_action_request(reviewer, action="publish_transcription_run"),
        queryset,
    )
    assert b"Start preview" in start_page.content
    assert f'value="{source.run.pk}"'.encode() in start_page.content

    response = publish_transcription_run(
        model_admin,
        bulk_action_request(
            reviewer,
            action="publish_transcription_run",
            run=str(source.run.pk),
            start="1",
        ),
        queryset,
    )
    publication = RunPublication.objects.get()
    assert response.status_code == 302
    assert response.url.endswith(f"/runpublication/{publication.pk}/change/")

    drain()
    status_admin = RunPublicationAdmin(RunPublication, admin.site)
    page = status_admin.change_view(
        bulk_action_request(reviewer), str(publication.pk)
    )
    assert b"Publish and approve" in page.content

    unconfirmed = status_admin.change_view(
        bulk_action_request(reviewer, publish="1"), str(publication.pk)
    )
    assert b"Check the confirmation box" in unconfirmed.content
    status_admin.change_view(
        bulk_action_request(reviewer, publish="1", confirmed="yes"),
        str(publication.pk),
    )
    publication.refresh_from_db()
    assert publication.state == State.PUBLISHING
    assert publication.confirmed_by == reviewer


@pytest.mark.django_db
@override_settings(CLAUDE_TRANSCRIPTION_ENABLED=False, ANTHROPIC_API_KEY="")
def test_worker_command_publishes_while_transcription_is_disabled(reviewer):
    schedule = canonical_schedule()
    source = agent_source(schedule)
    publication = start_publication(
        run=source.run, schedule_ids=[schedule.pk], user=reviewer
    )

    with patch.object(ClaudeTranscriptionWorker, "run_once") as transcribe:
        call_command(
            "run_transcription_worker",
            "--once",
            "--idle-when-disabled",
            "--liveness-file=",
        )

    transcribe.assert_not_called()
    assert publication.items.get().case == Case.PROMOTE


@pytest.mark.django_db
def test_run_filter_selects_schedules_covered_by_a_run(reviewer):
    from census.admin import TranscriptionRunFilter

    covered = canonical_schedule()
    source = agent_source(covered)
    canonical_schedule()
    model_admin = CensusScheduleAdmin(CensusSchedule, admin.site)
    request = RequestFactory().get(
        "/admin/census/censusschedule/", {"transcription_run": source.run.pk}
    )
    request.user = reviewer
    run_filter = TranscriptionRunFilter(
        request, request.GET.copy(), CensusSchedule, model_admin
    )

    assert list(run_filter.queryset(request, CensusSchedule.objects.all())) == [
        covered
    ]
