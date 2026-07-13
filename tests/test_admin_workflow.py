import pytest
from django.contrib import admin
from django.contrib.auth.models import Group, User
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory

from census.admin import (
    CensusScheduleAdmin,
    assign_to_me,
    mark_completed,
    mark_needs_review,
)
from census.models import CensusSchedule
from tests.factories import CensusScheduleFactory, ReligiousBodyFactory


@pytest.fixture
def transcriber(db):
    user = User.objects.create_user(username="transcriber", is_staff=True)
    group, _ = Group.objects.get_or_create(name="Transcribers")
    user.groups.add(group)
    return user


@pytest.fixture
def reviewer(db):
    user = User.objects.create_user(username="reviewer", is_staff=True)
    group, _ = Group.objects.get_or_create(name="Reviewers")
    user.groups.add(group)
    return user


def admin_request(user):
    request = RequestFactory().get("/admin/census/censusschedule/")
    request.user = user
    request.session = {}
    request._messages = FallbackStorage(request)
    return request


@pytest.mark.django_db
def test_transcriber_actions_stop_at_ready_for_review(transcriber):
    model_admin = CensusScheduleAdmin(CensusSchedule, admin.site)

    assert set(model_admin.get_actions(admin_request(transcriber))) == {
        "mark_in_progress",
        "mark_completed",
    }


@pytest.mark.django_db
def test_transcriber_cannot_edit_workflow_assignment_fields(transcriber):
    model_admin = CensusScheduleAdmin(CensusSchedule, admin.site)

    assert {
        "transcription_status",
        "assigned_transcriber",
        "assigned_reviewer",
    }.issubset(model_admin.get_readonly_fields(admin_request(transcriber)))


@pytest.mark.django_db
def test_reviewer_can_access_approval_action(reviewer):
    model_admin = CensusScheduleAdmin(CensusSchedule, admin.site)

    assert "mark_approved" in model_admin.get_actions(admin_request(reviewer))


@pytest.mark.django_db
def test_dual_role_staff_can_access_approval_action(transcriber):
    reviewer_group, _ = Group.objects.get_or_create(name="Reviewers")
    transcriber.groups.add(reviewer_group)
    model_admin = CensusScheduleAdmin(CensusSchedule, admin.site)

    assert "mark_approved" in model_admin.get_actions(admin_request(transcriber))


@pytest.mark.django_db
def test_dual_role_staff_assigns_self_as_reviewer(transcriber):
    reviewer_group, _ = Group.objects.get_or_create(name="Reviewers")
    transcriber.groups.add(reviewer_group)
    schedule = CensusScheduleFactory()
    model_admin = CensusScheduleAdmin(CensusSchedule, admin.site)

    assign_to_me(
        model_admin,
        admin_request(transcriber),
        CensusSchedule.objects.filter(pk=schedule.pk),
    )

    schedule.refresh_from_db()
    assert schedule.assigned_reviewer == transcriber
    assert schedule.assigned_transcriber is None


@pytest.mark.django_db
def test_transcriber_sees_only_assigned_schedules(transcriber):
    assigned = CensusScheduleFactory(assigned_transcriber=transcriber)
    CensusScheduleFactory()
    model_admin = CensusScheduleAdmin(CensusSchedule, admin.site)

    queryset = model_admin.get_queryset(admin_request(transcriber))

    assert list(queryset) == [assigned]


@pytest.mark.django_db
def test_dual_role_staff_sees_all_schedules(transcriber):
    reviewer_group, _ = Group.objects.get_or_create(name="Reviewers")
    transcriber.groups.add(reviewer_group)
    CensusScheduleFactory.create_batch(2)
    model_admin = CensusScheduleAdmin(CensusSchedule, admin.site)

    queryset = model_admin.get_queryset(admin_request(transcriber))

    assert queryset.count() == 2


@pytest.mark.django_db
def test_needs_review_requires_religious_body(transcriber):
    without_body = CensusScheduleFactory(transcription_status="in_progress")
    with_body = CensusScheduleFactory(transcription_status="in_progress")
    ReligiousBodyFactory(census_record=with_body)
    model_admin = CensusScheduleAdmin(CensusSchedule, admin.site)

    mark_needs_review(
        model_admin,
        admin_request(transcriber),
        CensusSchedule.objects.filter(pk__in=[without_body.pk, with_body.pk]),
    )

    without_body.refresh_from_db()
    with_body.refresh_from_db()
    assert without_body.transcription_status == "in_progress"
    assert with_body.transcription_status == "needs_review"


@pytest.mark.django_db
def test_completed_requires_religious_body(transcriber):
    without_body = CensusScheduleFactory(transcription_status="in_progress")
    with_body = CensusScheduleFactory(transcription_status="in_progress")
    ReligiousBodyFactory(census_record=with_body)
    model_admin = CensusScheduleAdmin(CensusSchedule, admin.site)

    mark_completed(
        model_admin,
        admin_request(transcriber),
        CensusSchedule.objects.filter(pk__in=[without_body.pk, with_body.pk]),
    )

    without_body.refresh_from_db()
    with_body.refresh_from_db()
    assert without_body.transcription_status == "in_progress"
    assert with_body.transcription_status == "completed"


@pytest.mark.django_db
def test_transcriber_save_starts_assigned_work(transcriber):
    schedule = CensusScheduleFactory(
        assigned_transcriber=transcriber,
        transcription_status="assigned",
    )
    model_admin = CensusScheduleAdmin(CensusSchedule, admin.site)

    model_admin.save_model(
        admin_request(transcriber),
        schedule,
        form=None,
        change=True,
    )

    schedule.refresh_from_db()
    assert schedule.transcription_status == "in_progress"


@pytest.mark.django_db
def test_transcriber_cannot_edit_submitted_schedule(transcriber):
    model_admin = CensusScheduleAdmin(CensusSchedule, admin.site)
    schedule = CensusScheduleFactory(
        assigned_transcriber=transcriber,
        transcription_status="needs_review",
    )

    assert not model_admin.has_change_permission(
        admin_request(transcriber), schedule
    )
