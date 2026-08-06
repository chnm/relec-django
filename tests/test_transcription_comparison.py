import pytest
from django.contrib.auth.models import Group, User
from django.core.exceptions import PermissionDenied
from django.urls import reverse

from census.models import ScheduleTranscription
from census.transcription.comparison import build_comparison
from tests.factories import (
    CensusScheduleFactory,
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
def test_reviewer_can_render_read_only_comparison(client, reviewer):
    schedule = CensusScheduleFactory()
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
        {"human": human.pk, "agent": agent.pk},
    )

    assert response.status_code == 200
    assert b"Compare transcriptions" in response.content
    assert b"human-review" in response.content
    assert b"agent-review" in response.content
    assert b"Blank vs zero" in response.content
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
        {"human": other.pk},
    )

    assert response.status_code == 200
    assert response.context["human_source"]["object"] == selected
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
