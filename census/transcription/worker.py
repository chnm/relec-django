"""Restart-safe orchestration for Anthropic message batches."""

import json
import logging
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import connection, models, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from census.models import ScheduleTranscription, TranscriptionBatch, TranscriptionJob

from .client import AmbiguousSubmissionError, ClaudeAPIError, ClaudeBatchClient
from .contracts import (
    CandidateValidationError,
    normalize_transport_candidate,
    validate_candidate,
)
from .payloads import PayloadError, build_batch_request

ACTIVE_BATCH_STATES = TranscriptionBatch.ACTIVE_STATES
SCHEDULER_ADVISORY_LOCK_ID = 6401926
PROGRESS_LOG_INTERVAL = timedelta(minutes=10)
logger = logging.getLogger(__name__)


class ClaudeTranscriptionWorker:
    def __init__(self, client=None):
        self.client = client or ClaudeBatchClient(
            settings.ANTHROPIC_API_KEY,
            settings.ANTHROPIC_API_BASE_URL,
            timeout=settings.CLAUDE_TRANSCRIPTION_REQUEST_TIMEOUT,
        )
        self._last_progress_log_at = {}

    def run_once(self):
        """Perform bounded work; safe to call repeatedly after restarts."""
        changed = self.recover_stale_preparations()
        changed = self.recover_stale_submissions() or changed
        batch = self._claim_pollable_batch()
        if batch:
            try:
                polled_to_completion = self._poll_or_collect(batch)
            except ClaudeAPIError:
                self._release_lease(batch)
                raise
            return polled_to_completion or changed
        if (
            self._active_batch_count()
            < settings.CLAUDE_TRANSCRIPTION_MAX_ACTIVE_BATCHES
        ):
            return self._prepare_and_submit_batch() or changed
        return changed

    @transaction.atomic
    def recover_stale_preparations(self):
        """Retry work that is known not to have reached the provider."""
        stale = TranscriptionBatch.objects.select_for_update(skip_locked=True).filter(
            state=TranscriptionBatch.State.QUEUED,
            lease_expires_at__lt=timezone.now(),
        )
        batch_ids = list(stale.values_list("pk", flat=True))
        if not batch_ids:
            return False
        TranscriptionJob.objects.filter(
            batch_id__in=batch_ids,
            state=TranscriptionJob.State.PREPARING,
        ).update(batch=None, state=TranscriptionJob.State.QUEUED)
        stale.update(
            state=TranscriptionBatch.State.FAILED,
            error={
                "type": "stale_preparation",
                "message": "Preparation lease expired before submission began; jobs were requeued.",
            },
        )
        return True

    @transaction.atomic
    def recover_stale_submissions(self):
        """Never retry a POST whose acceptance is unknown."""
        stale = TranscriptionBatch.objects.select_for_update(skip_locked=True).filter(
            state=TranscriptionBatch.State.SUBMITTING,
            lease_expires_at__lt=timezone.now(),
        )
        batch_ids = list(stale.values_list("pk", flat=True))
        if not batch_ids:
            return False
        stale.update(
            state=TranscriptionBatch.State.NEEDS_RECOVERY,
            error={
                "type": "stale_submission",
                "message": "Submission lease expired before a provider ID was stored.",
            },
        )
        TranscriptionJob.objects.filter(
            batch_id__in=batch_ids,
            state=TranscriptionJob.State.PREPARING,
        ).update(state=TranscriptionJob.State.NEEDS_RECOVERY)
        return True

    def _active_batch_count(self):
        return TranscriptionBatch.objects.filter(state__in=ACTIVE_BATCH_STATES).count()

    @transaction.atomic
    def _claim_queued_jobs(self):
        # A fixed transaction-scoped PostgreSQL advisory lock makes the global
        # active-batch cap reliable when multiple worker replicas start together.
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_try_advisory_xact_lock(%s)",
                [SCHEDULER_ADVISORY_LOCK_ID],
            )
            if not cursor.fetchone()[0]:
                return None, []
        if (
            self._active_batch_count()
            >= settings.CLAUDE_TRANSCRIPTION_MAX_ACTIVE_BATCHES
        ):
            return None, []

        jobs = list(
            TranscriptionJob.objects.select_for_update(skip_locked=True, of=("self",))
            .filter(state=TranscriptionJob.State.QUEUED, batch__isnull=True)
            .select_related(
                "run",
                "census_schedule__county__state",
                "census_schedule__schedule_denomination",
            )
            .order_by("queued_at", "pk")[: settings.CLAUDE_TRANSCRIPTION_BATCH_SIZE]
        )
        if not jobs:
            return None, []
        now = timezone.now()
        batch = TranscriptionBatch.objects.create(
            run=jobs[0].run,
            lease_token=uuid.uuid4(),
            lease_expires_at=now
            + timedelta(seconds=settings.CLAUDE_TRANSCRIPTION_LEASE_SECONDS),
            heartbeat_at=now,
        )
        same_run_jobs = [job for job in jobs if job.run_id == batch.run_id]
        for job in same_run_jobs:
            job.batch = batch
            job.state = TranscriptionJob.State.PREPARING
            job.save(update_fields=["batch", "state"])
        return batch, same_run_jobs

    def _prepare_and_submit_batch(self):
        batch, jobs = self._claim_queued_jobs()
        if not batch:
            return False
        logger.info(
            "Claude transcription work claimed run=%s batch=%s job_count=%s jobs=%s",
            batch.run.key,
            batch.pk,
            len(jobs),
            ",".join(job.custom_id for job in jobs),
        )

        payloads = []
        encoded_size = 0
        for job in jobs:
            try:
                payload = build_batch_request(job)
            except PayloadError as exc:
                self._fail_job(job, "payload_error", str(exc))
                continue
            payload_size = len(json.dumps(payload, separators=(",", ":")).encode())
            if (
                encoded_size + payload_size
                > settings.CLAUDE_TRANSCRIPTION_MAX_BATCH_BYTES
            ):
                if payloads:
                    self._requeue_job(job)
                else:
                    self._fail_job(
                        job,
                        "payload_too_large",
                        "One request exceeds the configured batch byte limit.",
                    )
                continue
            payloads.append(payload)
            encoded_size += payload_size
            self._heartbeat(batch)

        if not payloads:
            batch.state = TranscriptionBatch.State.FAILED
            batch.error = {"type": "empty_batch", "message": "No valid requests."}
            batch.save(update_fields=["state", "error", "updated_at"])
            return True

        batch = self._begin_submission(batch, len(payloads), encoded_size)
        if batch is None:
            return True

        try:
            snapshot = self.client.create_batch(payloads)
        except AmbiguousSubmissionError as exc:
            self._mark_ambiguous(batch, exc)
            logger.error(
                "Claude transcription submission outcome is ambiguous "
                "run=%s batch=%s status_code=%s error=%s",
                batch.run.key,
                batch.pk,
                exc.status_code,
                exc,
            )
            return True
        except ClaudeAPIError as exc:
            self._mark_rejected(batch, exc)
            logger.warning(
                "Claude transcription batch rejected run=%s batch=%s "
                "status_code=%s error=%s",
                batch.run.key,
                batch.pk,
                exc.status_code,
                exc,
            )
            return True

        self._record_submission(batch, snapshot)
        logger.info(
            "Claude transcription batch submitted run=%s batch=%s "
            "provider_batch=%s request_count=%s encoded_size_bytes=%s",
            batch.run.key,
            batch.pk,
            snapshot["id"],
            len(payloads),
            encoded_size,
        )
        self._last_progress_log_at[batch.pk] = timezone.now()
        return True

    @transaction.atomic
    def _begin_submission(self, batch, request_count, encoded_size):
        """Prove lease ownership before entering the ambiguous POST window."""
        claimed = TranscriptionBatch.objects.select_for_update().get(pk=batch.pk)
        if (
            claimed.state != TranscriptionBatch.State.QUEUED
            or claimed.lease_token != batch.lease_token
            or claimed.lease_expires_at is None
            or claimed.lease_expires_at < timezone.now()
        ):
            return None
        now = timezone.now()
        claimed.state = TranscriptionBatch.State.SUBMITTING
        claimed.request_count = request_count
        claimed.encoded_size_bytes = encoded_size
        claimed.lease_expires_at = now + timedelta(
            seconds=settings.CLAUDE_TRANSCRIPTION_LEASE_SECONDS
        )
        claimed.heartbeat_at = now
        claimed.save()
        return claimed

    @transaction.atomic
    def _record_submission(self, batch, snapshot):
        batch = TranscriptionBatch.objects.select_for_update().get(pk=batch.pk)
        now = timezone.now()
        batch.provider_batch_id = snapshot["id"]
        batch.provider_snapshot = snapshot
        batch.request_counts = snapshot.get("request_counts", {})
        batch.provider_expires_at = _datetime(snapshot.get("expires_at"))
        batch.provider_ended_at = _datetime(snapshot.get("ended_at"))
        batch.submitted_at = now
        batch.state = (
            TranscriptionBatch.State.COLLECTING
            if snapshot.get("processing_status") == "ended"
            else TranscriptionBatch.State.IN_PROGRESS
        )
        batch.lease_token = None
        batch.lease_expires_at = None
        batch.save()
        TranscriptionJob.objects.filter(
            batch=batch,
            state__in=[
                TranscriptionJob.State.PREPARING,
                TranscriptionJob.State.NEEDS_RECOVERY,
            ],
        ).update(state=TranscriptionJob.State.SUBMITTED, submitted_at=now)

    @transaction.atomic
    def _claim_pollable_batch(self):
        now = timezone.now()
        batch = (
            TranscriptionBatch.objects.select_for_update(skip_locked=True)
            .filter(
                state__in=[
                    TranscriptionBatch.State.IN_PROGRESS,
                    TranscriptionBatch.State.COLLECTING,
                ]
            )
            .filter(
                models.Q(lease_expires_at__isnull=True)
                | models.Q(lease_expires_at__lt=now)
            )
            .order_by("submitted_at", "pk")
            .first()
        )
        if batch:
            batch.lease_token = uuid.uuid4()
            batch.lease_expires_at = now + timedelta(
                seconds=settings.CLAUDE_TRANSCRIPTION_LEASE_SECONDS
            )
            batch.heartbeat_at = now
            batch.save(
                update_fields=[
                    "lease_token",
                    "lease_expires_at",
                    "heartbeat_at",
                    "updated_at",
                ]
            )
        return batch

    def _poll_or_collect(self, batch):
        if batch.state == TranscriptionBatch.State.IN_PROGRESS:
            previous_snapshot = batch.provider_snapshot or {}
            previous_status = previous_snapshot.get("processing_status")
            previous_counts = batch.request_counts or {}
            snapshot = self.client.retrieve_batch(batch.provider_batch_id)
            batch.provider_snapshot = snapshot
            batch.request_counts = snapshot.get("request_counts", {})
            batch.provider_expires_at = _datetime(snapshot.get("expires_at"))
            batch.provider_ended_at = _datetime(snapshot.get("ended_at"))
            self._log_batch_progress(
                batch,
                previous_status=previous_status,
                previous_counts=previous_counts,
            )
            if snapshot.get("processing_status") != "ended":
                batch.lease_token = None
                batch.lease_expires_at = None
                batch.save()
                # An unchanged provider poll is intentionally idle work. Returning
                # False makes the management command honor the configured interval
                # instead of immediately polling the same batch again.
                return False
            batch.state = TranscriptionBatch.State.COLLECTING
            batch.save()

        for result in self.client.iter_results(batch.provider_batch_id):
            recorded_job = self._record_result(batch, result)
            if recorded_job is not None:
                logger.info(
                    "Claude transcription result returned run=%s batch=%s "
                    "provider_batch=%s job=%s schedule=%s state=%s "
                    "input_tokens=%s output_tokens=%s",
                    recorded_job.run.key,
                    batch.pk,
                    batch.provider_batch_id,
                    recorded_job.custom_id,
                    recorded_job.census_schedule_id,
                    recorded_job.state,
                    recorded_job.total_input_tokens,
                    recorded_job.output_tokens or 0,
                )
            self._heartbeat(batch)

        missing_results = TranscriptionJob.objects.filter(
            batch=batch,
            state=TranscriptionJob.State.SUBMITTED,
            raw_result__isnull=True,
        )
        missing_count = missing_results.count()
        if missing_count:
            missing_results.update(
                state=TranscriptionJob.State.NEEDS_RECOVERY,
                error_type="missing_batch_result",
                error_message="No provider result matched this job's custom ID.",
            )
            batch.state = TranscriptionBatch.State.NEEDS_RECOVERY
            batch.error = {
                "type": "missing_batch_results",
                "message": f"{missing_count} submitted jobs had no matching result.",
            }
        else:
            batch.state = TranscriptionBatch.State.ENDED
        batch.collected_at = timezone.now()
        batch.lease_token = None
        batch.lease_expires_at = None
        batch.save()
        self._last_progress_log_at.pop(batch.pk, None)
        return True

    def _log_batch_progress(self, batch, *, previous_status, previous_counts):
        """Log changed provider counts or a bounded still-processing heartbeat."""
        now = timezone.now()
        provider_status = (batch.provider_snapshot or {}).get("processing_status")
        counts_changed = batch.request_counts != previous_counts
        status_changed = provider_status != previous_status
        last_logged_at = self._last_progress_log_at.get(batch.pk)
        interval_elapsed = (
            last_logged_at is None or now - last_logged_at >= PROGRESS_LOG_INTERVAL
        )
        if not counts_changed and not status_changed and not interval_elapsed:
            return

        reason = "changed" if counts_changed or status_changed else "periodic"
        logger.info(
            "Claude transcription batch status run=%s batch=%s provider_batch=%s "
            "provider_status=%s request_counts=%s reason=%s",
            batch.run.key,
            batch.pk,
            batch.provider_batch_id,
            provider_status,
            json.dumps(batch.request_counts, sort_keys=True),
            reason,
        )
        self._last_progress_log_at[batch.pk] = now

    @transaction.atomic
    def _record_result(self, batch, raw_result):
        custom_id = raw_result.get("custom_id")
        job = (
            TranscriptionJob.objects.select_for_update(of=("self",))
            .select_related("run", "census_schedule__county")
            .filter(batch=batch, custom_id=custom_id)
            .first()
        )
        if not job or job.raw_result is not None:
            return None

        job.raw_result = raw_result
        result = raw_result.get("result") or {}
        result_type = result.get("type", "unknown")
        job.completed_at = timezone.now()
        if result_type != "succeeded":
            job.state = {
                "expired": TranscriptionJob.State.EXPIRED,
                "canceled": TranscriptionJob.State.CANCELED,
            }.get(result_type, TranscriptionJob.State.FAILED)
            job.error_type = result_type
            job.error_message = json.dumps(result.get("error") or result)[:4000]
            job.save()
            return job

        message = result.get("message") or {}
        usage = message.get("usage") or {}
        job.provider_message_id = message.get("id")
        job.stop_reason = message.get("stop_reason")
        job.usage = usage
        for field in (
            "input_tokens",
            "output_tokens",
            "cache_creation_input_tokens",
            "cache_read_input_tokens",
        ):
            setattr(job, field, usage.get(field))
        if job.stop_reason != "end_turn":
            job.state = TranscriptionJob.State.INVALID
            job.error_type = "unexpected_stop_reason"
            job.error_message = f"Claude stopped with {job.stop_reason!r}."
            job.save()
            return job

        try:
            schema = job.run.metadata["schema"]
            candidate = normalize_transport_candidate(
                _message_json(message), schema=schema
            )
            validate_candidate(candidate, job.census_schedule, schema=schema)
        except (CandidateValidationError, ValueError, KeyError, TypeError) as exc:
            job.state = TranscriptionJob.State.INVALID
            job.error_type = "invalid_candidate"
            job.error_message = str(exc)[:4000]
            job.save()
            return job

        ScheduleTranscription.objects.get_or_create(
            census_schedule=job.census_schedule,
            run=job.run,
            defaults={"data": candidate},
        )
        job.state = TranscriptionJob.State.SUCCEEDED
        job.save()
        return job

    def _mark_ambiguous(self, batch, exc):
        batch.state = TranscriptionBatch.State.NEEDS_RECOVERY
        batch.error = _api_error("ambiguous_submission", exc)
        batch.save(update_fields=["state", "error", "updated_at"])
        TranscriptionJob.objects.filter(
            batch=batch,
            state__in=[
                TranscriptionJob.State.PREPARING,
                TranscriptionJob.State.NEEDS_RECOVERY,
            ],
        ).update(state=TranscriptionJob.State.NEEDS_RECOVERY)

    def _mark_rejected(self, batch, exc):
        batch.state = TranscriptionBatch.State.FAILED
        batch.error = _api_error("rejected_submission", exc)
        batch.save(update_fields=["state", "error", "updated_at"])
        TranscriptionJob.objects.filter(
            batch=batch,
            state__in=[
                TranscriptionJob.State.PREPARING,
                TranscriptionJob.State.NEEDS_RECOVERY,
            ],
        ).update(
            state=TranscriptionJob.State.FAILED,
            error_type="batch_rejected",
            error_message=str(exc),
            completed_at=timezone.now(),
        )

    def _fail_job(self, job, error_type, message):
        job.state = TranscriptionJob.State.FAILED
        job.error_type = error_type
        job.error_message = message
        job.completed_at = timezone.now()
        job.save()

    def _requeue_job(self, job):
        job.batch = None
        job.state = TranscriptionJob.State.QUEUED
        job.save(update_fields=["batch", "state"])

    def _heartbeat(self, batch):
        now = timezone.now()
        TranscriptionBatch.objects.filter(pk=batch.pk).update(
            heartbeat_at=now,
            lease_expires_at=now
            + timedelta(seconds=settings.CLAUDE_TRANSCRIPTION_LEASE_SECONDS),
        )

    def _release_lease(self, batch):
        TranscriptionBatch.objects.filter(pk=batch.pk).update(
            lease_token=None, lease_expires_at=None
        )


def _message_json(message):
    text_blocks = [
        block.get("text")
        for block in message.get("content", [])
        if block.get("type") == "text" and block.get("text")
    ]
    if len(text_blocks) != 1:
        raise ValueError("Expected exactly one text content block.")
    return json.loads(text_blocks[0])


def _datetime(value):
    return parse_datetime(value) if value else None


def _api_error(error_type, exc):
    return {
        "type": error_type,
        "message": str(exc),
        "status_code": exc.status_code,
        "response": exc.response,
    }
