import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from census.models import TranscriptionJob
from religious_ecologies.admin import _get_dashboard_data_sync
from tests.factories import (
    CensusScheduleFactory,
    ScheduleTranscriptionFactory,
    TranscriptionJobFactory,
)


@pytest.mark.django_db
def test_dashboard_metrics_distinguish_approval_and_review_readiness():
    schedules = {
        status: CensusScheduleFactory(transcription_status=status)
        for status in (
            "unassigned",
            "assigned",
            "in_progress",
            "needs_review",
            "completed",
            "approved",
        )
    }
    job = TranscriptionJobFactory(
        census_schedule=schedules["unassigned"],
        state=TranscriptionJob.State.SUCCEEDED,
    )
    ScheduleTranscriptionFactory(
        census_schedule=schedules["unassigned"],
        run=job.run,
    )

    context = _get_dashboard_data_sync(include_ai_usage=True)

    assert context["total_records"] == 6
    assert context["ready_for_review_count"] == 1
    assert context["imported_needs_review_count"] == 1
    assert context["needs_review_count"] == 2
    assert context["ai_ready_review_count"] == 1
    assert context["approved_count"] == 1
    assert context["approval_percentage"] == 16.7


@pytest.mark.django_db
def test_admin_overview_renders_operational_layout_and_accessible_charts(client):
    user = User.objects.create_superuser(
        username="dashboard-admin",
        email="dashboard@example.test",
        password="test-password",
    )
    CensusScheduleFactory(transcription_status="completed")
    client.force_login(user)

    response = client.get(reverse("admin:index"))

    assert response.status_code == 200
    assert b"Ready for Human Review" in response.content
    assert b"AI Candidates Ready" in response.content
    assert b"Schedules Approved" in response.content
    assert b"Project Complete" not in response.content
    assert b"Needs Attention" in response.content
    assert b"AI Review Queue" in response.content
    assert b"Recently Updated Schedules" in response.content
    assert b'indexAxis: "y"' in response.content
    assert b'aria-label="Horizontal bar chart of schedules by workflow status"' in (
        response.content
    )
    assert b"View workflow counts as text" in response.content
    assert b"chart.js@4.4.7" in response.content
