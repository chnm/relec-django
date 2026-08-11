import pytest
from django.contrib import admin
from django.contrib.auth.models import Group, User
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory, override_settings

from census.admin import (
    AITranscriptionFilter,
    CensusScheduleAdmin,
    TranscriptionRunAdmin,
    assign_to_me,
    mark_completed,
    mark_needs_review,
    queue_claude_transcription,
)
from census.models import CensusSchedule, TranscriptionRun
from tests.factories import (
    CensusScheduleFactory,
    ReligiousBodyFactory,
    ScheduleTranscriptionFactory,
    TranscriptionJobFactory,
    TranscriptionRunFactory,
)


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


def admin_post_request(user, data):
    request = RequestFactory().post("/admin/census/censusschedule/", data=data)
    request.user = user
    request.session = {}
    request._messages = FallbackStorage(request)
    return request


def ai_status_filter(user, value):
    model_admin = CensusScheduleAdmin(CensusSchedule, admin.site)
    request = RequestFactory().get(
        "/admin/census/censusschedule/",
        {"ai_status": value},
    )
    request.user = user
    return AITranscriptionFilter(
        request,
        request.GET.copy(),
        CensusSchedule,
        model_admin,
    ), request


@pytest.mark.django_db
def test_ai_status_filter_uses_latest_job_and_legacy_candidates(reviewer):
    not_queued = CensusScheduleFactory()
    queued = CensusScheduleFactory()
    processing = CensusScheduleFactory()
    transcribed = CensusScheduleFactory()
    legacy_transcribed = CensusScheduleFactory()
    failed = CensusScheduleFactory()
    needs_recovery = CensusScheduleFactory()
    TranscriptionJobFactory(
        census_schedule=queued,
        state="preparing",
    )
    TranscriptionJobFactory(
        census_schedule=processing,
        state="submitted",
    )
    TranscriptionJobFactory(
        census_schedule=transcribed,
        state="succeeded",
    )
    ScheduleTranscriptionFactory(
        census_schedule=transcribed,
        run=TranscriptionRunFactory(kind="agent"),
    )
    ScheduleTranscriptionFactory(
        census_schedule=legacy_transcribed,
        run=TranscriptionRunFactory(kind="agent"),
    )
    TranscriptionJobFactory(
        census_schedule=failed,
        state="invalid",
    )
    TranscriptionJobFactory(
        census_schedule=needs_recovery,
        state="needs_recovery",
    )

    expected = {
        "not_queued": {not_queued},
        "queued": {queued},
        "processing": {processing},
        "transcribed": {transcribed, legacy_transcribed},
        "failed": {failed},
        "needs_recovery": {needs_recovery},
    }
    for status, schedules in expected.items():
        status_filter, request = ai_status_filter(reviewer, status)
        queryset = status_filter.queryset(request, CensusSchedule.objects.all())
        assert set(queryset) == schedules


@pytest.mark.django_db
def test_ai_status_is_displayed_in_schedule_list(reviewer):
    schedule = CensusScheduleFactory()
    TranscriptionJobFactory(census_schedule=schedule, state="submitted")
    model_admin = CensusScheduleAdmin(CensusSchedule, admin.site)

    annotated = model_admin.get_queryset(admin_request(reviewer)).get(pk=schedule.pk)

    assert "ai_status_display" in model_admin.list_display
    assert "Processing" in model_admin.ai_status_display(annotated)


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
def test_reviewer_can_view_read_only_transcription_runs(reviewer):
    model_admin = TranscriptionRunAdmin(TranscriptionRun, admin.site)

    assert model_admin.has_module_permission(admin_request(reviewer))
    assert model_admin.has_view_permission(admin_request(reviewer))
    assert not model_admin.has_change_permission(admin_request(reviewer))


@pytest.mark.django_db
@override_settings(APPLICATION_REVISION="revision-for-admin-preview")
def test_claude_action_confirmation_uses_initial_values(reviewer):
    schedule = CensusScheduleFactory()
    model_admin = CensusScheduleAdmin(CensusSchedule, admin.site)
    request = admin_post_request(
        reviewer,
        {"_selected_action": [schedule.pk], "action": "queue_claude_transcription"},
    )

    response = queue_claude_transcription(
        model_admin,
        request,
        CensusSchedule.objects.filter(pk=schedule.pk),
    )

    assert response.status_code == 200
    assert b"This field is required" not in response.content
    assert b"claude-" in response.content
    assert b"revision-for-admin-preview" in response.content
    assert b"This is a job count" in response.content
    assert b"predicted usage amount" in response.content
    assert b"Frozen pricing estimate" in response.content


@pytest.mark.django_db
@override_settings(
    APPLICATION_REVISION="",
    CLAUDE_TRANSCRIPTION_ENABLED=True,
    ANTHROPIC_API_KEY="",
)
def test_claude_action_treats_application_revision_as_optional(reviewer):
    schedule = CensusScheduleFactory()
    model_admin = CensusScheduleAdmin(CensusSchedule, admin.site)
    request = admin_post_request(
        reviewer,
        {"_selected_action": [schedule.pk], "action": "queue_claude_transcription"},
    )

    response = queue_claude_transcription(
        model_admin,
        request,
        CensusSchedule.objects.filter(pk=schedule.pk),
    )

    assert response.status_code == 200
    assert b"Not recorded" in response.content
    assert b"Configuration required" not in response.content


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

    assert not model_admin.has_change_permission(admin_request(transcriber), schedule)
