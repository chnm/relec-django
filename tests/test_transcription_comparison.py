import pytest
from django.contrib.auth.models import Group, User
from django.core.exceptions import PermissionDenied
from django.test import Client
from django.urls import reverse

from census.models import ScheduleTranscription
from census.transcription.comparison import build_comparison
from census.transcription.reconciliation import (
    build_reconciliation_preview,
    serialize_canonical,
)
from tests.factories import (
    CensusScheduleFactory,
    ReligiousBodyFactory,
    ScheduleTranscriptionFactory,
    TranscriptionRunFactory,
)


def _row(comparison, section_title, label):
    section = next(
        section
        for section in comparison["sections"]
        if section["title"] == section_title
    )
    return next(row for row in section["rows"] if row["label"] == label)


def test_comparison_aligns_human_and_agent_shapes_without_hiding_blank_zero():
    human = {
        "schedule_fields": {
            "respondent_name": "Leon Allen",
            "respondent_title": "Clerk",
            "num_assistant_pastors": None,
        },
        "religious_bodies": [
            {
                "name": "Advent",
                "urban_rural_code": "Rural",
                "expenses": "600.00",
                "membership": [{"members_under_13": None}],
            }
        ],
        "clergy": [],
    }
    agent = {
        "schedule_fields": {
            "respondent": {"name": "Leon Allen", "title": "Clerk"},
            "num_assistant_pastors": 0,
        },
        "religious_bodies": [
            {
                "name": "Advent",
                "urban_rural_code": "R",
                "expenses": 600,
                "membership": {"members_under_13": 0},
            }
        ],
        "clergy": [],
    }

    comparison = build_comparison(human, agent)

    assert _row(comparison, "Respondent", "Name")["status"] == "same"
    assert _row(comparison, "Religious body 1", "Urban or rural")[
        "status"
    ] == "equivalent"
    assert _row(comparison, "Religious body 1", "Expenses")[
        "status"
    ] == "equivalent"
    assert _row(
        comparison, "Religious body 1: membership 1", "Members under 13"
    )["status"] == "blank_zero"
    assert comparison["counts"]["equivalent"] == 2
    assert comparison["counts"]["blank_zero"] == 2


@pytest.fixture
def reviewer(db):
    user = User.objects.create_user(username="comparison-reviewer", is_staff=True)
    group, _ = Group.objects.get_or_create(name="Reviewers")
    user.groups.add(group)
    return user


@pytest.fixture
def transcriber(db):
    user = User.objects.create_user(username="comparison-transcriber", is_staff=True)
    group, _ = Group.objects.get_or_create(name="Transcribers")
    user.groups.add(group)
    return user


@pytest.mark.django_db
def test_reviewer_can_render_reconciliation_preview_without_writes(client, reviewer):
    schedule = CensusScheduleFactory()
    ReligiousBodyFactory(
        census_record=schedule,
        denomination=schedule.schedule_denomination,
    )
    human_run = TranscriptionRunFactory(key="human-review", kind="human_snapshot")
    agent_run = TranscriptionRunFactory(
        key="agent-review",
        kind="agent",
        metadata={"model": "test-model", "contract_version": "test-v1"},
    )
    human = ScheduleTranscriptionFactory(
        census_schedule=schedule,
        run=human_run,
        data={"schedule_fields": {"num_assistant_pastors": None}},
    )
    agent = ScheduleTranscriptionFactory(
        census_schedule=schedule,
        run=agent_run,
        data={"schedule_fields": {"num_assistant_pastors": 0}},
    )
    before = list(
        ScheduleTranscription.objects.filter(census_schedule=schedule).values_list(
            "pk", "data"
        )
    )
    client.force_login(reviewer)

    response = client.get(
        reverse(
            "admin:census_censusschedule_compare_transcriptions",
            args=[schedule.pk],
        ),
        {"source": human.pk},
    )

    assert response.status_code == 200
    assert b"Reconcile and approve" in response.content
    assert b"human-review" in response.content
    assert b"Apply and approve" in response.content
    assert b"Choose what becomes canonical" not in response.content
    assert b"Preview mixed selection" not in response.content
    assert b"section-selection-status" in response.content
    assert b'aria-pressed="false"' in response.content
    assert b"comparison-source-value-current" in response.content
    assert b"comparison-source-value-candidate" in response.content
    assert b"updateSectionSelection" in response.content
    assert b"source-value-select" in response.content
    assert b"edited-choice" in response.content
    assert b"save-inline-edit" in response.content
    assert b'addEventListener("dblclick"' in response.content
    assert b"comparison-decision" not in response.content
    assert b'data-automatic-source="candidate"' in response.content
    assert b"carried from the selected evidence automatically" in response.content
    assert list(
        ScheduleTranscription.objects.filter(census_schedule=schedule).values_list(
            "pk", "data"
        )
    ) == before


@pytest.mark.django_db
def test_transcriber_cannot_access_comparison(client, transcriber):
    schedule = CensusScheduleFactory(assigned_transcriber=transcriber)
    client.force_login(transcriber)

    response = client.get(
        reverse(
            "admin:census_censusschedule_compare_transcriptions",
            args=[schedule.pk],
        )
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_comparison_source_selection_is_scoped_to_schedule(client, reviewer):
    schedule = CensusScheduleFactory()
    other_schedule = CensusScheduleFactory()
    ReligiousBodyFactory(
        census_record=schedule,
        denomination=schedule.schedule_denomination,
    )
    human_run = TranscriptionRunFactory(key="human-scoped", kind="human_snapshot")
    selected = ScheduleTranscriptionFactory(
        census_schedule=schedule,
        run=human_run,
        data={"schedule_fields": {"respondent_name": "Expected"}},
    )
    other_run = TranscriptionRunFactory(key="human-other", kind="human_snapshot")
    other = ScheduleTranscriptionFactory(
        census_schedule=other_schedule,
        run=other_run,
        data={"schedule_fields": {"respondent_name": "Wrong schedule"}},
    )
    client.force_login(reviewer)

    response = client.get(
        reverse(
            "admin:census_censusschedule_compare_transcriptions",
            args=[schedule.pk],
        ),
        {"source": other.pk},
    )

    assert response.status_code == 200
    assert response.context["selected_source"]["object"] == selected
    assert b"Wrong schedule" not in response.content


def test_comparison_view_rejects_non_reviewer_directly(transcriber):
    from django.contrib import admin
    from django.test import RequestFactory

    from census.admin import CensusScheduleAdmin
    from census.models import CensusSchedule

    schedule = CensusScheduleFactory(assigned_transcriber=transcriber)
    request = RequestFactory().get("/admin/compare/")
    request.user = transcriber
    model_admin = CensusScheduleAdmin(CensusSchedule, admin.site)

    with pytest.raises(PermissionDenied):
        model_admin.compare_transcriptions_view(request, str(schedule.pk))


@pytest.mark.django_db
def test_reviewer_can_approve_selected_result_from_interface(client, reviewer):
    schedule = CensusScheduleFactory(transcription_status="completed")
    ReligiousBodyFactory(
        census_record=schedule,
        denomination=schedule.schedule_denomination,
    )
    source = ScheduleTranscriptionFactory(
        census_schedule=schedule,
        run=TranscriptionRunFactory(kind="human_snapshot"),
        data=serialize_canonical(schedule),
    )
    preview = build_reconciliation_preview(schedule)
    client.force_login(reviewer)

    response = client.post(
        reverse(
            "admin:census_censusschedule_compare_transcriptions",
            args=[schedule.pk],
        ),
        {
            "source": source.pk,
            "expected_fingerprint": preview["before_fingerprint"],
            "confirmed": "yes",
            "notes": "Checked against the image.",
        },
    )

    schedule.refresh_from_db()
    assert response.status_code == 302
    assert schedule.transcription_status == "approved"
    reconciliation = schedule.reconciliations.get()
    assert reconciliation.outcome == "promoted_candidate"
    assert reconciliation.notes == "Checked against the image."


@pytest.mark.django_db
def test_direct_approval_still_requires_reviewer_confirmation(client, reviewer):
    schedule = CensusScheduleFactory(transcription_status="completed")
    ReligiousBodyFactory(
        census_record=schedule,
        denomination=schedule.schedule_denomination,
    )
    source = ScheduleTranscriptionFactory(
        census_schedule=schedule,
        run=TranscriptionRunFactory(kind="human_snapshot"),
        data=serialize_canonical(schedule),
    )
    preview = build_reconciliation_preview(schedule, source)
    client.force_login(reviewer)

    response = client.post(
        reverse(
            "admin:census_censusschedule_compare_transcriptions",
            args=[schedule.pk],
        ),
        {
            "source": source.pk,
            "expected_fingerprint": preview["before_fingerprint"],
        },
    )

    assert response.status_code == 200
    assert b"Confirm that you reviewed" in response.content
    assert not schedule.reconciliations.exists()


@pytest.mark.django_db
def test_reconciliation_post_is_csrf_protected(reviewer):
    schedule = CensusScheduleFactory()
    ReligiousBodyFactory(
        census_record=schedule,
        denomination=schedule.schedule_denomination,
    )
    source = ScheduleTranscriptionFactory(
        census_schedule=schedule,
        run=TranscriptionRunFactory(kind="human_snapshot"),
        data=serialize_canonical(schedule),
    )
    preview = build_reconciliation_preview(schedule)
    csrf_client = Client(enforce_csrf_checks=True)
    csrf_client.force_login(reviewer)

    response = csrf_client.post(
        reverse(
            "admin:census_censusschedule_compare_transcriptions",
            args=[schedule.pk],
        ),
        {
            "source": source.pk,
            "expected_fingerprint": preview["before_fingerprint"],
            "confirmed": "yes",
        },
    )

    assert response.status_code == 403
    schedule.refresh_from_db()
    assert schedule.transcription_status != "approved"


@pytest.mark.django_db
def test_interface_directly_applies_current_cell_selection(client, reviewer):
    schedule = CensusScheduleFactory(
        transcription_status="completed",
        respondent_name="Keep Human",
    )
    ReligiousBodyFactory(
        census_record=schedule,
        denomination=schedule.schedule_denomination,
    )
    candidate = serialize_canonical(schedule)
    candidate["schedule_fields"]["respondent_name"] = "Use Candidate"
    source = ScheduleTranscriptionFactory(
        census_schedule=schedule,
        run=TranscriptionRunFactory(kind="human_snapshot"),
        data=candidate,
    )
    initial = build_reconciliation_preview(schedule, source)
    url = reverse(
        "admin:census_censusschedule_compare_transcriptions",
        args=[schedule.pk],
    )
    client.force_login(reviewer)
    base_data = {
        "source": source.pk,
        "expected_fingerprint": initial["before_fingerprint"],
        "confirmed": "yes",
        "choice__schedule.respondent_name": "current",
    }

    applied = client.post(url, base_data)

    schedule.refresh_from_db()
    assert applied.status_code == 302
    assert schedule.transcription_status == "approved"
    assert schedule.respondent_name == "Keep Human"
    assert schedule.reconciliations.get().outcome == "retained_current"


@pytest.mark.django_db
def test_interface_directly_applies_inline_edit(client, reviewer):
    schedule = CensusScheduleFactory(
        transcription_status="completed",
        respondent_name="Current Name",
    )
    ReligiousBodyFactory(
        census_record=schedule,
        denomination=schedule.schedule_denomination,
    )
    candidate = serialize_canonical(schedule)
    candidate["schedule_fields"]["respondent_name"] = "Candidate Name"
    source = ScheduleTranscriptionFactory(
        census_schedule=schedule,
        run=TranscriptionRunFactory(kind="human_snapshot"),
        data=candidate,
    )
    initial = build_reconciliation_preview(schedule, source)
    url = reverse(
        "admin:census_censusschedule_compare_transcriptions",
        args=[schedule.pk],
    )
    client.force_login(reviewer)
    base_data = {
        "source": source.pk,
        "expected_fingerprint": initial["before_fingerprint"],
        "choice__schedule.respondent_name": "edited",
        "edit_base__schedule.respondent_name": "candidate",
        "edit__schedule.respondent_name": "Reviewer Name",
        "confirmed": "yes",
    }

    applied = client.post(url, base_data)

    schedule.refresh_from_db()
    assert applied.status_code == 302
    assert schedule.respondent_name == "Reviewer Name"
    reconciliation = schedule.reconciliations.get()
    assert reconciliation.outcome == "mixed"
    assert reconciliation.decisions["reviewer_overrides"] == [
        {
            "field": "schedule.respondent_name",
            "source": "edited",
            "base": "candidate",
            "value": "Reviewer Name",
        }
    ]
