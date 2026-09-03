import csv
import io
import json
from datetime import date, datetime
from decimal import Decimal

import pytest
from django.contrib import admin
from django.contrib.auth.models import Group, User
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory
from django.utils import timezone

from census.admin import TranscriptionRunAdmin
from census.models import TranscriptionJob, TranscriptionRun
from census.transcription.usage import (
    PricingConfigurationError,
    historical_cost_estimates,
    job_cost_breakdown,
    pricing_snapshot_for_model,
    usage_export_rows,
    usage_report,
)
from tests.factories import TranscriptionJobFactory, TranscriptionRunFactory


def pricing_catalog():
    return {
        "schema_version": 1,
        "currency": "USD",
        "unit": "per_million_tokens",
        "service_tier": "batch",
        "effective_date": "2026-08-11",
        "source": "https://example.test/pricing",
        "models": {
            "test-model": {
                "rates": {
                    "input_tokens": "1.00",
                    "output_tokens": "2.00",
                    "cache_creation_input_tokens": "1.25",
                    "cache_creation_1h_input_tokens": "2.00",
                    "cache_read_input_tokens": "0.10",
                }
            }
        },
    }


def priced_run():
    snapshot = pricing_snapshot_for_model(pricing_catalog(), "test-model")
    return TranscriptionRunFactory(
        metadata={
            "model": "test-model",
            "contract_version": "test-contract-v1",
            "pricing_snapshot": snapshot,
        }
    )


def usage_job(run, **kwargs):
    usage = {
        "input_tokens": 1_000_000,
        "output_tokens": 100_000,
        "cache_creation_input_tokens": 100_000,
        "cache_read_input_tokens": 200_000,
        "cache_creation": {
            "ephemeral_5m_input_tokens": 50_000,
            "ephemeral_1h_input_tokens": 25_000,
        },
    }
    defaults = {
        "run": run,
        "state": TranscriptionJob.State.SUCCEEDED,
        "usage": usage,
        "input_tokens": usage["input_tokens"],
        "output_tokens": usage["output_tokens"],
        "cache_creation_input_tokens": usage["cache_creation_input_tokens"],
        "cache_read_input_tokens": usage["cache_read_input_tokens"],
    }
    defaults.update(kwargs)
    return TranscriptionJobFactory(**defaults)


def admin_request(user, path):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.fixture
def reviewer(db):
    user = User.objects.create_user(username="usage-reviewer", is_staff=True)
    group, _ = Group.objects.get_or_create(name="Reviewers")
    user.groups.add(group)
    return user


def test_pricing_snapshot_is_normalized_and_model_specific():
    snapshot = pricing_snapshot_for_model(pricing_catalog(), "test-model")

    assert snapshot["model"] == "test-model"
    assert snapshot["rates"]["input_tokens"] == "1.00"
    assert "models" not in snapshot


def test_pricing_snapshot_rejects_incomplete_rates():
    catalog = pricing_catalog()
    del catalog["models"]["test-model"]["rates"]["output_tokens"]

    with pytest.raises(PricingConfigurationError, match="output_tokens"):
        pricing_snapshot_for_model(catalog, "test-model")


def test_pricing_snapshot_rejects_expired_temporary_rates():
    catalog = pricing_catalog()
    catalog["models"]["test-model"]["valid_through"] = "2000-01-01"

    with pytest.raises(PricingConfigurationError, match="expired"):
        pricing_snapshot_for_model(catalog, "test-model", as_of=date(2026, 8, 11))


def test_configured_sonnet_5_batch_rates_are_standard_and_unexpiring():
    # Anthropic made the $2/$10 introductory price permanent; the planned
    # 2026-09-01 increase did not happen, so the catalog must not expire.
    # Test the version-controlled default, not a local .env override.
    from config.settings import DEFAULT_CLAUDE_TRANSCRIPTION_PRICING

    snapshot = pricing_snapshot_for_model(
        DEFAULT_CLAUDE_TRANSCRIPTION_PRICING, "claude-sonnet-5"
    )

    assert snapshot["rates"]["input_tokens"] == "1.00"
    assert snapshot["rates"]["output_tokens"] == "5.00"
    assert "valid_through" not in snapshot


def test_admin_sidebar_sections_are_always_expanded():
    navigation = settings.UNFOLD["SIDEBAR"]["navigation"]

    assert all("collapsible" not in section for section in navigation)


def test_admin_sidebar_separates_project_management_from_data_models():
    navigation = {
        section["title"]: [item["title"] for item in section["items"]]
        for section in settings.UNFOLD["SIDEBAR"]["navigation"]
    }

    assert navigation["Project Management"] == [
        "Review Queue",
        "Imported - Needs Review",
        "Student Work - Ready",
        "AI Transcriptions - Ready for Review",
        "Assigned to Me",
    ]
    assert not set(navigation["Project Management"]).intersection(
        navigation["Transcriptions"]
    )
    assert "Census Schedules" in navigation["Transcriptions"]

    project_items = next(
        section["items"]
        for section in settings.UNFOLD["SIDEBAR"]["navigation"]
        if section["title"] == "Project Management"
    )
    ai_review_item = next(
        item
        for item in project_items
        if item["title"] == "AI Transcriptions - Ready for Review"
    )
    assert ai_review_item["link"](None) == (
        "/admin/census/censusschedule/?ai_status=transcribed"
    )
    assert callable(ai_review_item["permission"])


def test_recent_admin_actions_have_explicit_light_and_dark_text_contrast():
    css = (settings.BASE_DIR / "static/css/custom_unfold.css").read_text()

    assert "#recent-actions-module .actionlist > li {" in css
    assert "color: #111827 !important;" in css
    assert ".dark #recent-actions-module .actionlist > li {" in css
    assert "color: #f3f4f6 !important;" in css


@pytest.mark.django_db
def test_job_cost_uses_frozen_cache_specific_rates():
    cost = job_cost_breakdown(usage_job(priced_run()))

    assert cost["total"] == Decimal("1.363750")
    assert cost["token_counts"] == {
        "input_tokens": 1_000_000,
        "output_tokens": 100_000,
        "cache_creation_input_tokens": 75_000,
        "cache_creation_1h_input_tokens": 25_000,
        "cache_read_input_tokens": 200_000,
    }


@pytest.mark.django_db
def test_job_cost_rejects_usage_submitted_after_temporary_rate_expires():
    catalog = pricing_catalog()
    catalog["models"]["test-model"]["valid_through"] = "2026-08-31"
    snapshot = pricing_snapshot_for_model(
        catalog, "test-model", as_of=date(2026, 8, 11)
    )
    run = TranscriptionRunFactory(
        metadata={"model": "test-model", "pricing_snapshot": snapshot}
    )
    job = usage_job(
        run,
        submitted_at=timezone.make_aware(datetime(2026, 9, 1, 0, 1)),
    )

    assert job_cost_breakdown(job) is None


@pytest.mark.django_db
def test_usage_report_keeps_unpriced_history_visible():
    usage_job(priced_run())
    usage_job(TranscriptionRunFactory(metadata={"model": "legacy-model"}))

    report = usage_report()["overall"]

    assert report["total_runs"] == 2
    assert report["total_jobs"] == 2
    assert report["succeeded"] == 2
    assert report["priced_jobs"] == 1
    assert report["unpriced_jobs"] == 1
    assert report["total_cost"] == Decimal("1.363750")
    assert report["cost_per_success"] == Decimal("1.363750")


@pytest.mark.django_db
def test_usage_report_builds_recent_run_cost_chart_without_unpriced_runs():
    older = priced_run()
    newer = priced_run()
    usage_job(older)
    usage_job(newer, output_tokens=200_000)
    usage_job(TranscriptionRunFactory(metadata={"model": "legacy-model"}))

    chart = usage_report()["cost_per_success_chart"]

    assert [item["run"] for item in chart] == [newer, older]
    assert chart[0]["cost_per_success"] == Decimal("1.563750")
    assert chart[0]["width_percent"] == "100.00"
    assert chart[1]["width_percent"] == "87.21"
    assert all(item["model"] == "test-model" for item in chart)


@pytest.mark.django_db
def test_historical_cost_estimate_requires_three_priced_successes_per_model():
    run = priced_run()
    usage_job(run)
    usage_job(run)
    assert historical_cost_estimates() == {}

    usage_job(run)

    assert historical_cost_estimates() == {
        "test-model": {
            "cost_per_success": "1.363750",
            "priced_successes": 3,
            "currency": "USD",
        }
    }


@pytest.mark.django_db
def test_usage_export_is_flat_and_reproducible():
    job = usage_job(priced_run())

    row = next(usage_export_rows())

    assert row["job_custom_id"] == job.custom_id
    assert row["total_input_tokens"] == 1_300_000
    assert row["estimated_cost"] == "1.363750"
    assert row["pricing_effective_date"] == "2026-08-11"


@pytest.mark.django_db
def test_reviewer_can_open_usage_dashboard_and_exports(reviewer):
    usage_job(priced_run())
    model_admin = TranscriptionRunAdmin(TranscriptionRun, admin.site)

    dashboard = model_admin.usage_dashboard_view(
        admin_request(reviewer, "/admin/census/transcriptionrun/usage/")
    )
    csv_response = model_admin.usage_csv_view(
        admin_request(reviewer, "/admin/census/transcriptionrun/usage/export.csv")
    )
    json_response = model_admin.usage_json_view(
        admin_request(reviewer, "/admin/census/transcriptionrun/usage/export.json")
    )

    assert dashboard.status_code == 200
    assert b"Claude usage &amp; cost reporting" in dashboard.content
    assert b"Cost per successful transcription" in dashboard.content
    assert b"cost-chart-bar" in dashboard.content
    rows = list(csv.DictReader(io.StringIO(csv_response.content.decode())))
    assert rows[0]["estimated_cost"] == "1.363750"
    assert json.loads(json_response.content)[0]["estimated_cost"] == "1.363750"


@pytest.mark.django_db
def test_non_reviewer_cannot_open_usage_reporting():
    user = User.objects.create_user(username="ordinary-staff", is_staff=True)
    model_admin = TranscriptionRunAdmin(TranscriptionRun, admin.site)

    with pytest.raises(PermissionDenied):
        model_admin.usage_dashboard_view(
            admin_request(user, "/admin/census/transcriptionrun/usage/")
        )
