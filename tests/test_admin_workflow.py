import pytest
from django.contrib import admin
from django.contrib.auth.models import Group, User
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory, override_settings

from census.admin import (
    AITranscriptionFilter,
    CensusScheduleAdmin,
    CensusScheduleDenominationFilter,
    TranscriptionJobAdmin,
    TranscriptionRunAdmin,
    assign_to_me,
    mark_completed,
    mark_needs_review,
    queue_claude_transcription,
)
from census.models import CensusSchedule, TranscriptionJob, TranscriptionRun
from tests.factories import (
    CensusScheduleFactory,
    DenominationFactory,
    ReligiousBodyFactory,
    ScheduleTranscriptionFactory,
    TranscriptionBatchFactory,
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


@pytest.mark.django_db
def test_schedule_denomination_filter_includes_denomination_id(reviewer):
    denomination = DenominationFactory(
        name="Advent Christian Church",
        denomination_id="0-0-0",
    )
    model_admin = CensusScheduleAdmin(CensusSchedule, admin.site)
    request = admin_request(reviewer)
    field = CensusSchedule._meta.get_field("schedule_denomination")

    denomination_filter = CensusScheduleDenominationFilter(
        field,
        request,
        {},
        CensusSchedule,
        model_admin,
        "schedule_denomination",
    )

    assert (
        denomination.pk,
        "Advent Christian Church (0-0-0)",
    ) in denomination_filter.lookup_choices


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
def test_transcription_run_list_summarizes_campaign_progress(reviewer):
    run = TranscriptionRunFactory()
    TranscriptionJobFactory(run=run, state=TranscriptionJob.State.QUEUED)
    TranscriptionJobFactory(run=run, state=TranscriptionJob.State.SUBMITTED)
    TranscriptionJobFactory(run=run, state=TranscriptionJob.State.SUCCEEDED)
    TranscriptionJobFactory(run=run, state=TranscriptionJob.State.NEEDS_RECOVERY)
    model_admin = TranscriptionRunAdmin(TranscriptionRun, admin.site)

    annotated = model_admin.get_queryset(admin_request(reviewer)).get(pk=run.pk)

    assert model_admin.job_progress(annotated) == (
        "1/4 succeeded · 1 active · 1 queued · 1 attention"
    )


@pytest.mark.django_db
@override_settings(APPLICATION_REVISION="revision-for-admin-preview")
def test_claude_action_confirmation_uses_initial_values(reviewer):
    schedule = CensusScheduleFactory(original_image="census_images/originals/test.jpg")
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
    assert b"Leave blank to queue the complete ready selection" in response.content
    assert b"predicted usage amount" in response.content
    assert b"adaptive thinking is disabled" in response.content
    assert b"Frozen pricing estimate" in response.content
    assert b"Pilot size" in response.content
    assert b"Limit" not in response.content


@pytest.mark.django_db
def test_claude_confirmation_preserves_select_across_django_action_round_trip(
    reviewer,
):
    schedules = [
        CensusScheduleFactory(original_image="census_images/originals/test.jpg")
        for _ in range(2)
    ]
    model_admin = CensusScheduleAdmin(CensusSchedule, admin.site)
    request = admin_post_request(
        reviewer,
        {
            "_selected_action": [schedules[0].pk],
            "action": "queue_claude_transcription",
            "index": "0",
            "select_across": "1",
        },
    )

    response = model_admin.response_action(
        request,
        CensusSchedule.objects.filter(pk__in=[item.pk for item in schedules]),
    )

    assert response.status_code == 200
    assert b'name="select_across" value="1"' in response.content
    assert b"All matching records" in response.content

    confirmation_request = admin_post_request(
        reviewer,
        {
            "_selected_action": [schedules[0].pk],
            "action": "queue_claude_transcription",
            "index": "0",
            "select_across": "1",
            "apply": "1",
            "run_key": "select-across-round-trip",
            "model": "claude-sonnet-4-6",
            "pilot_size": "",
            "confirmation_job_count": "",
        },
    )
    confirmation_response = model_admin.response_action(
        confirmation_request,
        CensusSchedule.objects.filter(pk__in=[item.pk for item in schedules]),
    )

    assert confirmation_response.status_code == 302
    assert (
        TranscriptionRun.objects.get(
            key="select-across-round-trip"
        ).transcription_jobs.count()
        == 2
    )


@pytest.mark.django_db
@override_settings(CLAUDE_TRANSCRIPTION_ENABLED=True)
def test_claude_action_queues_the_full_ready_queryset_without_a_pilot(reviewer):
    schedules = [
        CensusScheduleFactory(original_image="census_images/originals/test.jpg")
        for _ in range(2)
    ]
    model_admin = CensusScheduleAdmin(CensusSchedule, admin.site)
    request = admin_post_request(
        reviewer,
        {
            "_selected_action": [schedules[0].pk],
            "action": "queue_claude_transcription",
            "select_across": "1",
            "apply": "1",
            "run_key": "full-denomination-campaign",
            "model": "claude-sonnet-4-6",
            "pilot_size": "",
            "confirmation_job_count": "",
        },
    )

    response = queue_claude_transcription(
        model_admin,
        request,
        CensusSchedule.objects.filter(pk__in=[item.pk for item in schedules]),
    )

    assert response.status_code == 302
    run = TranscriptionRun.objects.get(key="full-denomination-campaign")
    assert run.transcription_jobs.count() == 2


@pytest.mark.django_db
@override_settings(CLAUDE_TRANSCRIPTION_ENABLED=True)
def test_claude_action_locks_only_schedule_rows_from_admin_queryset(reviewer):
    schedule = CensusScheduleFactory(original_image="census_images/originals/test.jpg")
    model_admin = CensusScheduleAdmin(CensusSchedule, admin.site)
    request = admin_post_request(
        reviewer,
        {
            "_selected_action": [schedule.pk],
            "action": "queue_claude_transcription",
            "apply": "1",
            "run_key": "admin-queryset-locking",
            "model": "claude-sonnet-4-6",
            "pilot_size": "1",
            "confirmation_job_count": "",
        },
    )
    queryset = model_admin.get_queryset(request).filter(pk=schedule.pk)

    response = queue_claude_transcription(model_admin, request, queryset)

    assert response.status_code == 302
    run = TranscriptionRun.objects.get(key="admin-queryset-locking")
    assert list(
        run.transcription_jobs.values_list("census_schedule_id", flat=True)
    ) == [schedule.pk]


@pytest.mark.django_db
def test_reviewer_can_cancel_only_unclaimed_queued_jobs(reviewer):
    queued = TranscriptionJobFactory(state=TranscriptionJob.State.QUEUED)
    submitted = TranscriptionJobFactory(state=TranscriptionJob.State.SUBMITTED)
    batch = TranscriptionBatchFactory()
    claimed = TranscriptionJobFactory(
        run=batch.run,
        batch=batch,
        state=TranscriptionJob.State.PREPARING,
    )
    model_admin = TranscriptionJobAdmin(TranscriptionJob, admin.site)
    request = admin_post_request(reviewer, {})

    assert "cancel_queued_jobs" in model_admin.get_actions(request)

    model_admin.cancel_queued_jobs(
        request,
        TranscriptionJob.objects.filter(pk__in=[queued.pk, submitted.pk, claimed.pk]),
    )

    queued.refresh_from_db()
    submitted.refresh_from_db()
    claimed.refresh_from_db()
    assert queued.state == TranscriptionJob.State.CANCELED
    assert queued.error_type == "canceled_by_reviewer"
    assert queued.completed_at is not None
    assert queued.history.first().history_user == reviewer
    assert submitted.state == TranscriptionJob.State.SUBMITTED
    assert claimed.state == TranscriptionJob.State.PREPARING


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
