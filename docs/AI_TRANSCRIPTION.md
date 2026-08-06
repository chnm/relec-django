# Claude batch transcription

Issue #64 is implemented as an asynchronous, restart-safe candidate-generation
pipeline. It does not reconcile candidates or promote them into canonical census
models.

## Data model

- `TranscriptionRun` is immutable scholarly provenance. It freezes the model,
  prompt, candidate schema, provider transport schema, their SHA-256 hashes, launch
  selection, maximum output tokens, and an optional pricing snapshot.
- `TranscriptionBatch` is one Anthropic Message Batch submission. It stores the
  provider ID, status snapshots, request counts, timestamps, and a renewable worker
  lease.
- `TranscriptionJob` is one schedule attempt. It stores the untouched provider
  result and usage object plus denormalized input, output, cache-creation, and
  cache-read token counts.
- `ScheduleTranscription` is the immutable, locally validated candidate. Its foreign
  keys are protected from cascade deletion.

Runs and candidate outputs cannot be edited or deleted through normal model,
queryset, or admin paths. A new attempt belongs in a new run (or a later explicitly
designed retry workflow), never over an existing result.

## Configuration

The feature is disabled by default. Configure it through deployment secrets and
environment variables, never through an admin form:

```text
ANTHROPIC_API_KEY=...
CLAUDE_TRANSCRIPTION_ENABLED=True
CLAUDE_TRANSCRIPTION_MODELS=claude-sonnet-4-6
```

Optional controls:

```text
ANTHROPIC_API_BASE_URL=https://api.anthropic.com
CLAUDE_TRANSCRIPTION_MAX_TOKENS=4096
CLAUDE_TRANSCRIPTION_DEFAULT_RUN_LIMIT=10
CLAUDE_TRANSCRIPTION_MAX_RUN_LIMIT=100
CLAUDE_TRANSCRIPTION_BATCH_SIZE=25
CLAUDE_TRANSCRIPTION_MAX_ACTIVE_BATCHES=1
CLAUDE_TRANSCRIPTION_MAX_BATCH_BYTES=209715200
CLAUDE_TRANSCRIPTION_MAX_IMAGE_BYTES=10485760
CLAUDE_TRANSCRIPTION_LEASE_SECONDS=300
CLAUDE_TRANSCRIPTION_POLL_SECONDS=60
CLAUDE_TRANSCRIPTION_REQUEST_TIMEOUT=120
CLAUDE_TRANSCRIPTION_PRICING={}
```

`CLAUDE_TRANSCRIPTION_PRICING` is a JSON object captured unchanged in each run. It
allows later cost estimates to use the prices that staff intended at launch time;
provider-reported token counts remain the benchmark source of truth.
`CLAUDE_TRANSCRIPTION_MAX_IMAGE_BYTES` applies to the base64-encoded image, matching
the direct Claude API's image-size definition.

Anthropic defines total input usage as ordinary input tokens plus cache-creation and
cache-read input tokens. The admin run total uses that sum while preserving all
three components separately on every job and in the exact raw `usage` object.

## Admin workflow

Reviewers select schedules in the Census Schedule changelist and choose **Queue
selected schedules for Claude transcription**. The confirmation page reports:

- selected and image-eligible schedule counts;
- the prompt/schema version;
- whether the workflow is enabled and an API key is configured (never the key);
- run key, allowed model, and a hard-bounded schedule limit.

Confirmation only creates the immutable run and queued jobs. It does not make a
provider request from the web process. Run, batch, and job admin pages are read-only
and expose progress, errors, and token usage.

Once a schedule has both a human snapshot and a successful agent candidate,
reviewers can open **Compare transcriptions** from its admin change page. The
read-only comparison keeps the object-storage image visible beside aligned human
and agent fields, supports selecting among immutable runs, distinguishes blanks
from zeroes, and retains expandable raw JSON. Legacy human representations such as
decimal strings and `Rural`/`Urban` labels are normalized for display only; neither
source document nor canonical census data is changed. Repeated religious bodies,
memberships, and clergy are aligned by document order and labeled accordingly.

## Synchronizing object-storage image references

The production object store is the image source of truth, but each Django database
must still know the object key assigned to each schedule's `original_image` field.
Images are not copied when preparing a local database.

For a bounded local test, build a manifest from the public API without making any
production database or filesystem changes:

```bash
uv run python manage.py fetch_schedule_image_manifest schedule-images.csv \
  --limit 10 --page-size 10
```

This client requests only HTTPS API pages, uses the reduced `view=map` response,
retries transient failures, and applies a delay between pages. It extracts the
stable `resource_id` from `urls.self`, strips signatures and query parameters from
`urls.image`, and retains only validated `census_images/originals/` object keys. It
never downloads the image itself or persists a signed URL.

For a complete catalog synchronization, exporting the mapping directly on
production is more efficient and places less load on the public API:

```bash
uv run python manage.py export_schedule_image_manifest schedule-images.csv
```

The exporter includes only schedules with an image, writes through a temporary file,
and refuses to replace an existing manifest unless `--overwrite` is explicit. Move
the resulting CSV to the local environment through the normal administrative file
transfer process. The API-generated and production-exported manifests use the same
format and feed the same importer.

First verify one local link against the configured object storage without changing
the database:

```bash
uv run python manage.py import_schedule_image_manifest schedule-images.csv \
  --dry-run --limit 1 --verify-storage
```

Then import one verified link for a bounded Claude pilot:

```bash
uv run python manage.py import_schedule_image_manifest schedule-images.csv \
  --limit 1 --verify-storage
```

After the pilot, import the complete manifest:

```bash
uv run python manage.py import_schedule_image_manifest schedule-images.csv
```

The importer matches on `resource_id`, never a database primary key. It accepts only
keys under `census_images/originals/`, fills blank image fields only, reports missing
local schedules, and refuses conflicting links. It changes database references only:
it neither uploads nor downloads image objects. `--verify-storage` performs one
remote existence check per candidate key, so reserve a complete verified pass for
when that additional object-storage traffic is intentional.

The older `import_image_path` command populates legacy DataScribe/Omeka metadata and
does not set `original_image`. The older `fetch_omeka_images` command downloads and
uploads files and is not part of the object-storage manifest workflow.

## Worker and restart behavior

Run the worker separately from the public Django process:

```bash
uv run python manage.py run_transcription_worker
```

For one bounded scheduler iteration (useful in tests or a system timer):

```bash
uv run python manage.py run_transcription_worker --once
```

The Compose files define a `transcription-worker` using the same image, database,
media storage, and environment as the app. Local Compose places it behind the
`transcription` profile:

```bash
docker compose --profile transcription up
```

The worker is safe to restart while polling or collecting. PostgreSQL row locks
prevent simultaneous claims; expiring leases allow another worker to resume. The
provider batch ID is persisted before polling. Results are matched by opaque
`custom_id`, because Anthropic does not guarantee result ordering. Collection is
idempotent and already-recorded raw results are skipped.

Preparation has its own lease. If a worker dies while reading or encoding images,
the expired preparation is marked failed and its unsubmitted jobs are safely
requeued. Immediately before POST, the worker rechecks lease ownership under a row
lock; a worker that lost its lease cannot submit.

A submission POST is different: if a connection error, timeout, HTTP 5xx, or worker
death makes acceptance ambiguous, the batch and jobs move to `needs_recovery`.
They are not automatically retried, preventing duplicate paid submissions. An
expired `submitting` lease is quarantined the same way. A provider HTTP 4xx is a
definite rejection and is recorded as failed.

## Prompt and schema

The tracked contract lives in:

- `census/transcription/prompts/relec-1926-v1.md`
- `census/transcription/schemas/relec-1926-v1.json`

Anthropic currently limits structured-output schemas to 16 union-typed parameters.
The candidate schema exceeds that because archival blanks are meaningful nulls.
At request time Django deterministically derives and freezes a provider transport
schema that uses unambiguous sentinels: empty string for nullable text, `-1` for
nullable nonnegative integers, and `-1/0/1` for nullable booleans. Constraints that
Anthropic does not support in structured-output schemas, such as `minimum` and
`minItems`, are moved into field descriptions in the transport schema. The original
candidate schema retains those constraints for local validation. The untouched
provider result is retained on the job; Django converts the transport values,
validates the candidate schema, and confirms any selected populated-place ID belongs
to the schedule county before creating `ScheduleTranscription`.

## Testing

Tests use fake clients and local media storage. They make no live Anthropic or S3
requests. Covered behavior includes contract validation, payload construction,
selection limits, out-of-order results, usage aggregation, provider-evidence
immutability, ambiguous submissions, stale submission leases, and protected raw
outputs.

Provider references: [Message Batches API](https://platform.claude.com/docs/en/api/messages/batches/create)
and [Structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs).
