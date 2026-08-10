import json
from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone

from census.models import (
    CensusSchedule,
    ScheduleTranscription,
    TranscriptionBatch,
    TranscriptionJob,
)
from census.transcription.client import AmbiguousSubmissionError
from census.transcription.contracts import (
    CandidateValidationError,
    load_contract,
    normalize_transport_candidate,
    validate_candidate,
)
from census.transcription.payloads import build_batch_request
from census.transcription.services import LaunchError, launch_transcription_run
from census.transcription.worker import ClaudeTranscriptionWorker
from tests.factories import (
    CensusScheduleFactory,
    PopulatedPlaceFactory,
    TranscriptionBatchFactory,
    TranscriptionJobFactory,
    TranscriptionRunFactory,
)


@pytest.fixture(autouse=True)
def local_media_storage(settings, tmp_path):
    settings.STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    }
    settings.MEDIA_ROOT = tmp_path


def candidate(place_id=None):
    membership = {
        "male_members": 10,
        "female_members": 12,
        "total_members_by_sex": 22,
        "members_under_13": None,
        "members_13_and_older": None,
        "total_members_by_age": None,
        "sunday_school_num_officers_teachers": None,
        "sunday_school_num_scholars": None,
        "vbs_num_officers_teachers": None,
        "vbs_num_scholars": None,
        "weekday_num_officers_teachers": None,
        "weekday_num_scholars": None,
        "parochial_num_administrators": None,
        "parochial_num_elementary_teachers": None,
        "parochial_num_secondary_teachers": None,
        "parochial_num_elementary_scholars": None,
        "parochial_num_secondary_scholars": None,
    }
    return {
        "schema_version": "relec-1926-v1",
        "schedule_fields": {
            "populated_place_verbatim": "Fairview",
            "populated_place_id": place_id,
            "county_verbatim": "Example",
            "state_verbatim": "VA",
            "num_assistant_pastors": 0,
            "respondent": {
                "name": None,
                "title": None,
                "po_address": None,
                "date_signed": None,
            },
            "processing": {
                "date_received": None,
                "district_stamp": None,
                "denomination_code_stamp": None,
            },
            "marginalia": [],
            "ai_notes": None,
        },
        "religious_bodies": [
            {
                "name": "Example Church",
                "census_code": "0-1",
                "division": None,
                "address": None,
                "urban_rural_code": "R",
                "membership": membership,
                "num_edifices": 1,
                "edifice_value": None,
                "edifice_debt": None,
                "has_pastors_residence": False,
                "residence_value": None,
                "residence_debt": None,
                "expenses": None,
                "benevolences": None,
                "total_expenditures": None,
            }
        ],
        "clergy": [],
    }


def frozen_run_metadata(**overrides):
    contract = load_contract()
    metadata = {
        "model": "test-model",
        "max_tokens": 1024,
        "prompt": contract["prompt"],
        "schema": contract["schema"],
        "transport_schema": contract["transport_schema"],
    }
    metadata.update(overrides)
    return metadata


@pytest.mark.django_db
def test_contract_validates_shape_and_county_local_place():
    schedule = CensusScheduleFactory()
    place = PopulatedPlaceFactory(county=schedule.county, place_id=8123)

    assert validate_candidate(candidate(place.place_id), schedule)["schema_version"]

    other_place = PopulatedPlaceFactory(place_id=9999)
    with pytest.raises(CandidateValidationError, match="not one of"):
        validate_candidate(candidate(other_place.place_id), schedule)


def test_transport_schema_avoids_nullable_unions_and_normalizes_sentinels():
    contract = load_contract()

    def keyword_count(node, keyword):
        if isinstance(node, list):
            return sum(keyword_count(item, keyword) for item in node)
        if not isinstance(node, dict):
            return 0
        own = int(keyword in node)
        return own + sum(
            keyword_count(value, keyword) for value in node.values()
        )

    def keyword_values(node, keyword):
        if isinstance(node, list):
            for item in node:
                yield from keyword_values(item, keyword)
        elif isinstance(node, dict):
            if keyword in node:
                yield node[keyword]
            for value in node.values():
                yield from keyword_values(value, keyword)

    transport_schema = contract["transport_schema"]
    assert keyword_count(transport_schema, "minimum") == 0
    assert keyword_count(transport_schema, "minItems") == 0
    assert not any(
        isinstance(node, list)
        for node in keyword_values(transport_schema, "type")
    )

    candidate_members = contract["schema"]["$defs"]["membership"]["properties"]
    assert candidate_members["male_members"]["minimum"] == 0
    assert contract["schema"]["properties"]["religious_bodies"]["minItems"] == 1

    transport_members = transport_schema["$defs"]["membership"]["properties"]
    assert transport_members["male_members"]["type"] == "integer"
    assert "Non-null values must be at least 0." in transport_members[
        "male_members"
    ]["description"]
    assert "Transport: -1 means null." in transport_members["male_members"][
        "description"
    ]

    transport = candidate()
    transport["schedule_fields"]["populated_place_verbatim"] = ""
    transport["schedule_fields"]["num_assistant_pastors"] = -1
    body = transport["religious_bodies"][0]
    body["has_pastors_residence"] = 0
    body["membership"]["members_under_13"] = -1

    normalized = normalize_transport_candidate(transport)

    assert normalized["schedule_fields"]["populated_place_verbatim"] is None
    assert normalized["schedule_fields"]["num_assistant_pastors"] is None
    assert normalized["religious_bodies"][0]["has_pastors_residence"] is False
    assert normalized["religious_bodies"][0]["membership"]["members_under_13"] is None


@pytest.mark.django_db
@override_settings(
    CLAUDE_TRANSCRIPTION_ENABLED=True,
    ANTHROPIC_API_KEY="",
    CLAUDE_TRANSCRIPTION_MODELS=["test-model"],
    CLAUDE_TRANSCRIPTION_MAX_TOKENS=2048,
    CLAUDE_TRANSCRIPTION_PRICING={"test-model": {"input_per_million": "1.00"}},
    APPLICATION_REVISION="0123456789abcdef0123456789abcdef01234567",
)
def test_launch_freezes_contract_and_honors_limit(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    schedules = [
        CensusScheduleFactory(
            original_image=SimpleUploadedFile(
                f"schedule-{index}.jpg", b"image bytes", content_type="image/jpeg"
            )
        )
        for index in range(3)
    ]

    run = launch_transcription_run(
        queryset=CensusSchedule.objects.filter(pk__in=[item.pk for item in schedules]),
        key="claude-test-run",
        model="test-model",
        limit=2,
    )

    contract = load_contract()
    assert run.transcription_jobs.count() == 2
    assert run.metadata["prompt"] == contract["prompt"]
    assert run.metadata["schema_sha256"] == contract["schema_sha256"]
    assert (
        run.metadata["application_revision"]
        == "0123456789abcdef0123456789abcdef01234567"
    )
    assert run.metadata["pricing_snapshot"]["test-model"]["input_per_million"] == "1.00"


@pytest.mark.django_db
@override_settings(
    CLAUDE_TRANSCRIPTION_ENABLED=True,
    ANTHROPIC_API_KEY="",
    APPLICATION_REVISION="",
)
def test_launch_allows_missing_application_revision():
    schedule = CensusScheduleFactory(original_image="census_images/originals/test.jpg")

    run = launch_transcription_run(
        queryset=CensusSchedule.objects.filter(pk=schedule.pk),
        key="missing-application-revision",
        model="claude-sonnet-4-6",
        limit=1,
    )

    assert run.metadata["application_revision"] is None
    assert run.transcription_jobs.count() == 1


@pytest.mark.django_db
@override_settings(CLAUDE_TRANSCRIPTION_ENABLED=True, ANTHROPIC_API_KEY="")
def test_launch_does_not_require_an_api_key_in_the_web_process():
    """Only the worker talks to the provider, so the key stays out of the web tier."""
    schedule = CensusScheduleFactory(original_image="census_images/originals/test.jpg")

    run = launch_transcription_run(
        queryset=CensusSchedule.objects.filter(pk=schedule.pk),
        key="no-api-key-in-web-process",
        model="claude-sonnet-4-6",
        limit=1,
    )

    assert run.transcription_jobs.count() == 1


@pytest.mark.django_db
@override_settings(CLAUDE_TRANSCRIPTION_ENABLED=False, ANTHROPIC_API_KEY="test-key")
def test_launch_refuses_when_the_workflow_is_disabled():
    """CLAUDE_TRANSCRIPTION_ENABLED is now the only launch gate."""
    schedule = CensusScheduleFactory(original_image="census_images/originals/test.jpg")

    with pytest.raises(LaunchError):
        launch_transcription_run(
            queryset=CensusSchedule.objects.filter(pk=schedule.pk),
            key="workflow-disabled",
            model="claude-sonnet-4-6",
            limit=1,
        )

    assert not TranscriptionJob.objects.exists()


@pytest.mark.django_db
@override_settings(CLAUDE_TRANSCRIPTION_MAX_IMAGE_BYTES=1024)
def test_payload_contains_base64_image_context_and_structured_output(
    tmp_path, settings
):
    settings.MEDIA_ROOT = tmp_path
    schedule = CensusScheduleFactory(
        original_image=SimpleUploadedFile(
            "schedule.jpg", b"image bytes", content_type="image/jpeg"
        )
    )
    frozen_prompt = "Use the frozen prompt from run provenance."
    frozen_transport_schema = {"type": "object", "additionalProperties": False}
    run = TranscriptionRunFactory(
        metadata=frozen_run_metadata(
            prompt=frozen_prompt,
            transport_schema=frozen_transport_schema,
        )
    )
    job = TranscriptionJobFactory(census_schedule=schedule, run=run)

    payload = build_batch_request(job)

    params = payload["params"]
    assert len(payload["custom_id"]) <= 64
    assert params["messages"][0]["content"][0]["type"] == "image"
    assert params["system"] == frozen_prompt
    assert params["output_config"]["format"]["schema"] == frozen_transport_schema
    assert params["output_config"]["format"]["type"] == "json_schema"
    assert "populated_place_candidates" in params["messages"][0]["content"][1]["text"]


class SuccessfulBatchClient:
    def __init__(self, candidate_data):
        self.candidate_data = candidate_data

    def create_batch(self, requests_payload):
        self.custom_ids = [item["custom_id"] for item in requests_payload]
        return {
            "id": "msgbatch_test",
            "processing_status": "in_progress",
            "request_counts": {"processing": len(requests_payload)},
            "expires_at": "2026-08-07T00:00:00Z",
            "ended_at": None,
        }

    def retrieve_batch(self, provider_batch_id):
        assert provider_batch_id == "msgbatch_test"
        return {
            "id": provider_batch_id,
            "processing_status": "ended",
            "request_counts": {"succeeded": len(self.custom_ids)},
            "expires_at": "2026-08-07T00:00:00Z",
            "ended_at": "2026-08-06T13:00:00Z",
        }

    def iter_results(self, provider_batch_id):
        for custom_id in reversed(self.custom_ids):
            yield {
                "custom_id": custom_id,
                "result": {
                    "type": "succeeded",
                    "message": {
                        "id": f"msg_{custom_id}",
                        "stop_reason": "end_turn",
                        "content": [
                            {"type": "text", "text": json.dumps(self.candidate_data)}
                        ],
                        "usage": {
                            "input_tokens": 123,
                            "output_tokens": 45,
                            "cache_creation_input_tokens": 10,
                            "cache_read_input_tokens": 20,
                        },
                    },
                },
            }


@pytest.mark.django_db(transaction=True)
@override_settings(
    CLAUDE_TRANSCRIPTION_BATCH_SIZE=25,
    CLAUDE_TRANSCRIPTION_MAX_ACTIVE_BATCHES=1,
    CLAUDE_TRANSCRIPTION_MAX_BATCH_BYTES=1024 * 1024,
    CLAUDE_TRANSCRIPTION_MAX_IMAGE_BYTES=1024,
    CLAUDE_TRANSCRIPTION_LEASE_SECONDS=60,
)
def test_worker_submits_collects_out_of_order_and_records_usage(
    tmp_path, settings, monkeypatch
):
    settings.MEDIA_ROOT = tmp_path
    run = TranscriptionRunFactory(metadata=frozen_run_metadata())
    monkeypatch.setattr(
        "census.transcription.contracts.load_contract",
        lambda: (_ for _ in ()).throw(AssertionError("loaded current contract")),
    )
    for index in range(2):
        schedule = CensusScheduleFactory(
            original_image=SimpleUploadedFile(
                f"schedule-{index}.jpg", b"image bytes", content_type="image/jpeg"
            )
        )
        TranscriptionJobFactory(census_schedule=schedule, run=run)
    worker = ClaudeTranscriptionWorker(client=SuccessfulBatchClient(candidate()))

    assert worker.run_once()
    assert (
        TranscriptionBatch.objects.get().state == TranscriptionBatch.State.IN_PROGRESS
    )
    assert worker.run_once()

    assert ScheduleTranscription.objects.filter(run=run).count() == 2
    assert set(run.transcription_jobs.values_list("state", flat=True)) == {"succeeded"}
    assert run.token_usage == {
        "input_tokens": 246,
        "output_tokens": 90,
        "cache_creation_input_tokens": 20,
        "cache_read_input_tokens": 40,
        "total_input_tokens": 306,
    }
    batch = TranscriptionBatch.objects.get()
    assert batch.state == TranscriptionBatch.State.ENDED
    assert batch.collected_at is not None


class AmbiguousClient:
    def create_batch(self, requests_payload):
        raise AmbiguousSubmissionError("connection lost")


@pytest.mark.django_db(transaction=True)
@override_settings(
    CLAUDE_TRANSCRIPTION_BATCH_SIZE=25,
    CLAUDE_TRANSCRIPTION_MAX_ACTIVE_BATCHES=1,
    CLAUDE_TRANSCRIPTION_MAX_BATCH_BYTES=1024 * 1024,
    CLAUDE_TRANSCRIPTION_MAX_IMAGE_BYTES=1024,
    CLAUDE_TRANSCRIPTION_LEASE_SECONDS=60,
)
def test_ambiguous_submission_is_never_automatically_retried(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    schedule = CensusScheduleFactory(
        original_image=SimpleUploadedFile(
            "schedule.jpg", b"image bytes", content_type="image/jpeg"
        )
    )
    run = TranscriptionRunFactory(metadata=frozen_run_metadata())
    TranscriptionJobFactory(census_schedule=schedule, run=run)

    worker = ClaudeTranscriptionWorker(client=AmbiguousClient())
    assert worker.run_once()

    assert (
        TranscriptionBatch.objects.get().state
        == TranscriptionBatch.State.NEEDS_RECOVERY
    )
    assert TranscriptionJob.objects.get().state == TranscriptionJob.State.NEEDS_RECOVERY
    assert not worker.run_once()


@pytest.mark.django_db
def test_stale_submission_lease_requires_manual_recovery():
    batch = TranscriptionBatchFactory(
        state=TranscriptionBatch.State.SUBMITTING,
        lease_expires_at=timezone.now() - timedelta(seconds=1),
    )
    job = TranscriptionJobFactory(
        run=batch.run,
        batch=batch,
        state=TranscriptionJob.State.PREPARING,
    )
    worker = ClaudeTranscriptionWorker(client=object())

    assert worker.recover_stale_submissions()
    batch.refresh_from_db()
    job.refresh_from_db()
    assert batch.state == TranscriptionBatch.State.NEEDS_RECOVERY
    assert job.state == TranscriptionJob.State.NEEDS_RECOVERY


@pytest.mark.django_db
def test_stale_preparation_is_safely_requeued_without_provider_retry():
    batch = TranscriptionBatchFactory(
        state=TranscriptionBatch.State.QUEUED,
        lease_expires_at=timezone.now() - timedelta(seconds=1),
    )
    job = TranscriptionJobFactory(
        run=batch.run,
        batch=batch,
        state=TranscriptionJob.State.PREPARING,
    )
    worker = ClaudeTranscriptionWorker(client=object())

    assert worker.recover_stale_preparations()
    batch.refresh_from_db()
    job.refresh_from_db()
    assert batch.state == TranscriptionBatch.State.FAILED
    assert job.state == TranscriptionJob.State.QUEUED
    assert job.batch is None


@pytest.mark.django_db
def test_provider_evidence_is_immutable():
    job = TranscriptionJobFactory(
        raw_result={"custom_id": "result"},
        usage={"input_tokens": 2},
        input_tokens=2,
    )
    job.input_tokens = 3
    with pytest.raises(ValidationError, match="provider evidence is immutable"):
        job.save()

    with pytest.raises(ValidationError, match="Immutable job fields"):
        TranscriptionJob.objects.filter(pk=job.pk).update(input_tokens=4)
