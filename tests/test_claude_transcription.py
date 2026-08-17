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
from census.transcription.services import (
    LaunchError,
    launch_transcription_run,
    worker_status,
)
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
        return own + sum(keyword_count(value, keyword) for value in node.values())

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
        isinstance(node, list) for node in keyword_values(transport_schema, "type")
    )

    candidate_members = contract["schema"]["$defs"]["membership"]["properties"]
    assert candidate_members["male_members"]["minimum"] == 0
    assert contract["schema"]["properties"]["religious_bodies"]["minItems"] == 1

    transport_members = transport_schema["$defs"]["membership"]["properties"]
    assert transport_members["male_members"]["type"] == "integer"
    assert (
        "Non-null values must be at least 0."
        in transport_members["male_members"]["description"]
    )
    assert (
        "Transport: -1 means null." in transport_members["male_members"]["description"]
    )

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
    CLAUDE_TRANSCRIPTION_PRICING={
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
    },
    APPLICATION_REVISION="0123456789abcdef0123456789abcdef01234567",
)
def test_launch_freezes_contract_and_honors_pilot_size(tmp_path, settings):
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
        pilot_size=2,
    )

    contract = load_contract()
    assert run.transcription_jobs.count() == 2
    assert (
        TranscriptionJob.history.filter(
            id__in=run.transcription_jobs.values_list("pk", flat=True),
            history_type="+",
        ).count()
        == 2
    )
    assert run.metadata["selection_count"] == 3
    assert run.metadata["eligible_count"] == 3
    assert run.metadata["pilot_size"] == 2
    assert "thinking" not in run.metadata
    assert run.metadata["prompt"] == contract["prompt"]
    assert run.metadata["schema_sha256"] == contract["schema_sha256"]
    assert (
        run.metadata["application_revision"]
        == "0123456789abcdef0123456789abcdef01234567"
    )
    assert run.metadata["pricing_snapshot"] == {
        "schema_version": 1,
        "currency": "USD",
        "unit": "per_million_tokens",
        "service_tier": "batch",
        "effective_date": "2026-08-11",
        "source": "https://example.test/pricing",
        "model": "test-model",
        "rates": {
            "input_tokens": "1.00",
            "output_tokens": "2.00",
            "cache_creation_input_tokens": "1.25",
            "cache_creation_1h_input_tokens": "2.00",
            "cache_read_input_tokens": "0.10",
        },
    }


@pytest.mark.django_db
@override_settings(
    CLAUDE_TRANSCRIPTION_ENABLED=True,
    CLAUDE_TRANSCRIPTION_MODELS=["claude-sonnet-5"],
)
def test_sonnet_5_run_freezes_disabled_thinking_in_payload(monkeypatch):
    monkeypatch.setattr(
        "census.transcription.services.pricing_snapshot_for_model",
        lambda catalog, model: {"model": model},
    )
    schedule = CensusScheduleFactory(
        original_image=SimpleUploadedFile(
            "schedule.jpg", b"image bytes", content_type="image/jpeg"
        )
    )

    run = launch_transcription_run(
        queryset=CensusSchedule.objects.filter(pk=schedule.pk),
        key="sonnet-5-thinking-disabled",
        model="claude-sonnet-5",
    )

    assert run.metadata["thinking"] == {"type": "disabled"}
    payload = build_batch_request(run.transcription_jobs.get())
    assert payload["params"]["thinking"] == {"type": "disabled"}


@pytest.mark.django_db
@override_settings(CLAUDE_TRANSCRIPTION_ENABLED=True)
def test_launch_queues_the_complete_ready_selection_by_default():
    schedules = [
        CensusScheduleFactory(original_image="census_images/originals/test.jpg")
        for _ in range(3)
    ]

    run = launch_transcription_run(
        queryset=CensusSchedule.objects.filter(
            pk__in=[schedule.pk for schedule in schedules]
        ),
        key="complete-selection",
        model="claude-sonnet-4-6",
    )

    assert set(run.transcription_jobs.values_list("census_schedule_id", flat=True)) == {
        schedule.pk for schedule in schedules
    }
    assert run.metadata["pilot_size"] is None
    assert run.metadata["schedule_count"] == 3


@pytest.mark.django_db
@override_settings(
    CLAUDE_TRANSCRIPTION_ENABLED=True,
    CLAUDE_TRANSCRIPTION_LARGE_RUN_THRESHOLD=5000,
    CLAUDE_TRANSCRIPTION_BATCH_SIZE=25,
)
def test_launch_creates_one_denomination_scale_campaign():
    CensusSchedule.objects.bulk_create(
        [
            CensusSchedule(
                resource_id=50_000 + index,
                schedule_id=f"scale-{index}",
                schedule_title=f"Scale schedule {index}",
                original_image=f"census_images/originals/scale-{index}.jpg",
            )
            for index in range(2000)
        ],
        batch_size=1000,
    )

    run = launch_transcription_run(
        queryset=CensusSchedule.objects.filter(schedule_id__startswith="scale-"),
        key="denomination-scale-campaign",
        model="claude-sonnet-4-6",
    )

    assert run.transcription_jobs.count() == 2000
    assert run.metadata["schedule_count"] == 2000
    assert run.metadata["estimated_batch_count"] == 80


@pytest.mark.django_db
@override_settings(CLAUDE_TRANSCRIPTION_ENABLED=True)
def test_launch_excludes_active_work_but_allows_retranscription():
    queued = CensusScheduleFactory(original_image="census_images/originals/queued.jpg")
    recovering = CensusScheduleFactory(
        original_image="census_images/originals/recovering.jpg"
    )
    succeeded = CensusScheduleFactory(
        original_image="census_images/originals/succeeded.jpg"
    )
    TranscriptionJobFactory(
        census_schedule=queued,
        state=TranscriptionJob.State.QUEUED,
    )
    TranscriptionJobFactory(
        census_schedule=recovering,
        state=TranscriptionJob.State.NEEDS_RECOVERY,
    )
    TranscriptionJobFactory(
        census_schedule=succeeded,
        state=TranscriptionJob.State.SUCCEEDED,
    )

    run = launch_transcription_run(
        queryset=CensusSchedule.objects.filter(
            pk__in=[queued.pk, recovering.pk, succeeded.pk]
        ),
        key="retranscription-is-allowed",
        model="claude-sonnet-4-6",
    )

    assert list(
        run.transcription_jobs.values_list("census_schedule_id", flat=True)
    ) == [succeeded.pk]


@pytest.mark.django_db
@override_settings(
    CLAUDE_TRANSCRIPTION_ENABLED=True,
    CLAUDE_TRANSCRIPTION_LARGE_RUN_THRESHOLD=2,
)
def test_launch_requires_exact_confirmation_for_a_large_run():
    schedules = [
        CensusScheduleFactory(original_image="census_images/originals/test.jpg")
        for _ in range(2)
    ]
    queryset = CensusSchedule.objects.filter(
        pk__in=[schedule.pk for schedule in schedules]
    )

    with pytest.raises(LaunchError, match="Confirm the exact planned job count"):
        launch_transcription_run(
            queryset=queryset,
            key="unconfirmed-large-run",
            model="claude-sonnet-4-6",
        )

    run = launch_transcription_run(
        queryset=queryset,
        key="confirmed-large-run",
        model="claude-sonnet-4-6",
        confirmed_job_count=2,
    )
    assert run.transcription_jobs.count() == 2


@pytest.mark.django_db
@override_settings(
    CLAUDE_TRANSCRIPTION_ENABLED=True,
    CLAUDE_TRANSCRIPTION_MAX_RUN_JOBS=2,
    CLAUDE_TRANSCRIPTION_LARGE_RUN_THRESHOLD=100,
)
def test_launch_enforces_the_emergency_job_ceiling():
    schedules = [
        CensusScheduleFactory(original_image="census_images/originals/test.jpg")
        for _ in range(3)
    ]

    with pytest.raises(LaunchError, match="emergency ceiling"):
        launch_transcription_run(
            queryset=CensusSchedule.objects.filter(
                pk__in=[schedule.pk for schedule in schedules]
            ),
            key="above-ceiling",
            model="claude-sonnet-4-6",
        )


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
        )

    assert not TranscriptionJob.objects.exists()


@pytest.mark.django_db
def test_worker_status_reports_idle_without_claiming_the_process_is_up():
    """An empty database means "no work", which is not evidence of liveness."""
    status = worker_status()

    assert status["tone"] == "idle"
    assert status["label"] == "Idle"
    assert status["last_activity"] is None
    assert "cannot confirm" in status["detail"]


@pytest.mark.django_db
def test_worker_status_reports_a_freshly_heartbeating_batch_as_working():
    now = timezone.now()
    TranscriptionBatchFactory(
        state=TranscriptionBatch.State.IN_PROGRESS,
        heartbeat_at=now - timedelta(seconds=5),
    )

    status = worker_status(now=now)

    assert status["tone"] == "ok"
    assert status["label"] == "Working"


@pytest.mark.django_db
@override_settings(CLAUDE_TRANSCRIPTION_LEASE_SECONDS=300)
def test_worker_status_flags_an_active_batch_with_a_lapsed_heartbeat():
    """A hung worker looks exactly like this from the web tier."""
    now = timezone.now()
    TranscriptionBatchFactory(
        state=TranscriptionBatch.State.COLLECTING,
        heartbeat_at=now - timedelta(seconds=1200),
    )

    status = worker_status(now=now)

    assert status["tone"] == "alert"
    assert status["label"] == "Stalled"


@pytest.mark.django_db
def test_worker_status_surfaces_batches_awaiting_manual_recovery():
    now = timezone.now()
    TranscriptionBatchFactory(
        state=TranscriptionBatch.State.NEEDS_RECOVERY,
        heartbeat_at=now - timedelta(seconds=30),
    )

    status = worker_status(now=now)

    assert status["tone"] == "warn"
    assert status["label"] == "Needs recovery"
    assert "1 batch requires" in status["detail"]


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
    assert "thinking" not in params
    assert len(payload["custom_id"]) <= 64
    assert params["messages"][0]["content"][0]["type"] == "image"
    assert params["system"] == frozen_prompt
    assert params["output_config"]["format"]["schema"] == frozen_transport_schema
    assert params["output_config"]["format"]["type"] == "json_schema"
    assert "populated_place_candidates" in params["messages"][0]["content"][1]["text"]


class SuccessfulBatchClient:
    def __init__(self, candidate_data):
        self.candidate_data = candidate_data
        self.batch_count = 0
        self.batch_sizes = []

    def create_batch(self, requests_payload):
        self.batch_count += 1
        self.batch_sizes.append(len(requests_payload))
        self.custom_ids = [item["custom_id"] for item in requests_payload]
        return {
            "id": (
                "msgbatch_test"
                if self.batch_count == 1
                else f"msgbatch_test_{self.batch_count}"
            ),
            "processing_status": "in_progress",
            "request_counts": {"processing": len(requests_payload)},
            "expires_at": "2026-08-07T00:00:00Z",
            "ended_at": None,
        }

    def retrieve_batch(self, provider_batch_id):
        assert provider_batch_id.startswith("msgbatch_test")
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


@pytest.mark.django_db
def test_max_tokens_result_is_retained_as_invalid_without_candidate():
    batch = TranscriptionBatchFactory(state=TranscriptionBatch.State.COLLECTING)
    job = TranscriptionJobFactory(
        run=batch.run,
        batch=batch,
        state=TranscriptionJob.State.SUBMITTED,
    )
    raw_result = {
        "custom_id": job.custom_id,
        "result": {
            "type": "succeeded",
            "message": {
                "id": "msg_truncated",
                "stop_reason": "max_tokens",
                "content": [
                    {"type": "thinking", "thinking": "", "signature": "opaque"},
                    {
                        "type": "text",
                        "text": '{"schema_version":"relec-1926-v1","ai_notes":"A red pencil ',
                    },
                ],
                "usage": {
                    "input_tokens": 16056,
                    "output_tokens": 4096,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0,
                    "output_tokens_details": {"thinking_tokens": 3756},
                },
            },
        },
    }

    recorded = ClaudeTranscriptionWorker(client=object())._record_result(
        batch, raw_result
    )

    job.refresh_from_db()
    assert recorded.pk == job.pk
    assert job.state == TranscriptionJob.State.INVALID
    assert job.stop_reason == "max_tokens"
    assert job.error_type == "unexpected_stop_reason"
    assert job.output_tokens == 4096
    assert job.usage["output_tokens_details"]["thinking_tokens"] == 3756
    assert job.raw_result == raw_result
    assert not ScheduleTranscription.objects.filter(
        census_schedule=job.census_schedule,
        run=job.run,
    ).exists()


@pytest.mark.django_db(transaction=True)
@override_settings(
    CLAUDE_TRANSCRIPTION_BATCH_SIZE=25,
    CLAUDE_TRANSCRIPTION_MAX_ACTIVE_BATCHES=1,
    CLAUDE_TRANSCRIPTION_MAX_BATCH_BYTES=1024 * 1024,
    CLAUDE_TRANSCRIPTION_MAX_IMAGE_BYTES=1024,
    CLAUDE_TRANSCRIPTION_LEASE_SECONDS=60,
)
def test_worker_submits_collects_out_of_order_and_records_usage(
    tmp_path, settings, monkeypatch, caplog
):
    caplog.set_level("INFO", logger="census.transcription.worker")
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
    messages = [record.getMessage() for record in caplog.records]
    assert any(
        "work claimed" in message and "job_count=2" in message for message in messages
    )
    assert any(
        "batch submitted" in message and "provider_batch=msgbatch_test" in message
        for message in messages
    )
    assert sum("result returned" in message for message in messages) == 2
    assert all("image bytes" not in message for message in messages)


@pytest.mark.django_db(transaction=True)
@override_settings(
    CLAUDE_TRANSCRIPTION_BATCH_SIZE=2,
    CLAUDE_TRANSCRIPTION_MAX_ACTIVE_BATCHES=1,
    CLAUDE_TRANSCRIPTION_MAX_BATCH_BYTES=1024 * 1024,
    CLAUDE_TRANSCRIPTION_MAX_IMAGE_BYTES=1024,
    CLAUDE_TRANSCRIPTION_LEASE_SECONDS=60,
)
def test_worker_auto_chunks_one_run_into_multiple_provider_batches(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    run = TranscriptionRunFactory(metadata=frozen_run_metadata())
    for index in range(5):
        schedule = CensusScheduleFactory(
            original_image=SimpleUploadedFile(
                f"schedule-{index}.jpg", b"image bytes", content_type="image/jpeg"
            )
        )
        TranscriptionJobFactory(census_schedule=schedule, run=run)
    client = SuccessfulBatchClient(candidate())
    worker = ClaudeTranscriptionWorker(client=client)

    for _ in range(6):
        assert worker.run_once()

    assert client.batch_sizes == [2, 2, 1]
    assert run.transcription_batches.count() == 3
    assert set(run.transcription_jobs.values_list("state", flat=True)) == {"succeeded"}
    assert not worker.run_once()


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
