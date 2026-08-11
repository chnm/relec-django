# Claude batch transcription

Issue #64 is implemented as an asynchronous, restart-safe candidate-generation
pipeline. It does not reconcile candidates or promote them into canonical census
models.

## Data model

- `TranscriptionRun` is immutable scholarly provenance. It freezes the model,
  prompt, candidate schema, provider transport schema, their SHA-256 hashes, launch
  selection, maximum output tokens, optional application revision, and a validated
  model-specific Batch pricing snapshot.
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
CLAUDE_TRANSCRIPTION_ENABLED=True
CLAUDE_TRANSCRIPTION_MODELS=claude-sonnet-4-6,claude-sonnet-5
ANTHROPIC_API_KEY=...   # transcription-worker environment only
```

`ANTHROPIC_API_KEY` belongs in the transcription worker's environment and nowhere
else. Only the worker calls the provider; the web process never reads the key, and
`launch_transcription_run` gates on `CLAUDE_TRANSCRIPTION_ENABLED` alone so that
queueing works without the secret being present in the internet-facing container.
Set `CLAUDE_TRANSCRIPTION_ENABLED` for both services: the web process needs it to
permit queueing, and the worker needs it to leave its idle loop.

`APPLICATION_REVISION` is optional best-effort provenance. When deployment automation
supplies an exact Git commit, immutable image digest, or release identifier, the value
is copied into the run. Its absence never blocks a run; prompt/schema contents and
hashes remain the reproducibility contract. Do not maintain this setting manually in
development unless a specific experiment needs it.

Optional controls:

```text
ANTHROPIC_API_BASE_URL=https://api.anthropic.com
APPLICATION_REVISION=<deployed-git-commit-or-image-digest>
CLAUDE_TRANSCRIPTION_MAX_TOKENS=4096
CLAUDE_TRANSCRIPTION_LARGE_RUN_THRESHOLD=100
CLAUDE_TRANSCRIPTION_MAX_RUN_JOBS=10000
CLAUDE_TRANSCRIPTION_BATCH_SIZE=25
CLAUDE_TRANSCRIPTION_MAX_ACTIVE_BATCHES=1
CLAUDE_TRANSCRIPTION_MAX_BATCH_BYTES=209715200
CLAUDE_TRANSCRIPTION_MAX_IMAGE_BYTES=10485760
CLAUDE_TRANSCRIPTION_LEASE_SECONDS=300
CLAUDE_TRANSCRIPTION_POLL_SECONDS=60
CLAUDE_TRANSCRIPTION_REQUEST_TIMEOUT=120
CLAUDE_TRANSCRIPTION_PRICING=<optional validated JSON catalog override>
```

The application includes a version-controlled Batch pricing catalog for its default
Claude model. `CLAUDE_TRANSCRIPTION_PRICING` can replace that catalog with a
deployment-approved JSON object when models or prices change. Before queueing, the
selected model must have nonnegative decimal rates for ordinary input, output,
5-minute cache creation, 1-hour cache creation, and cache reads, plus currency,
service tier, effective date, and source metadata. A normalized model-specific copy
is frozen in the run; current prices are never applied retroactively. Existing runs
created before validated snapshots remain explicitly unpriced. An absent or empty
environment override uses the version-controlled default, which keeps deployments
that previously set the old `{}` placeholder from blocking new runs.

Temporary rates may include `valid_through` in `YYYY-MM-DD` form. The launch path
rejects an expired rate rather than silently estimating new work with an obsolete
price. Cost reporting also leaves a job unpriced if its submission timestamp falls
after the frozen rate's validity window. Model entries can override catalog-level
dates and other metadata.

The version-controlled default uses Anthropic's published Claude Sonnet 4.6 Batch
rates effective 2026-08-11: $1.50 ordinary input, $7.50 output, $1.875 5-minute
cache writes, $3.00 1-hour cache writes, and $0.15 cache reads per million tokens.
It also records Claude Sonnet 5's introductory Batch rates through 2026-08-31:
$1.00 input, $5.00 output, $1.25 5-minute cache writes, $2.00 1-hour cache writes,
and $0.10 cache reads per million tokens. Sonnet 5's standard rates begin
2026-09-01, so deployments must update the catalog before launching it after the
introductory period.
Confirm the [official pricing page](https://platform.claude.com/docs/en/about-claude/pricing)
before changing the catalog.
`CLAUDE_TRANSCRIPTION_MAX_IMAGE_BYTES` applies to the base64-encoded image, matching
the direct Claude API's image-size definition.

Anthropic defines total input usage as ordinary input tokens plus cache-creation and
cache-read input tokens. The admin run total uses that sum while preserving all
three components separately on every job and in the exact raw `usage` object.

## Admin workflow

Reviewers select schedules in the Census Schedule changelist and choose **Queue
selected schedules for Claude transcription**. The confirmation page reports:

Django's **Select all matching records** choice is preserved through the
confirmation form, so reviewers may filter to a denomination, select the whole
result set across every admin page, and launch it as one campaign.

- selected, ready, missing-image, and already-active schedule counts. A schedule is
  ready when it has an original image and no queued, preparing, submitted, or
  manual-recovery job. Successful and other terminal attempts remain eligible for
  intentional retranscription in a new run;
- the prompt/schema version;
- whether the workflow is enabled, plus an optional application revision when one
  was supplied automatically. It reports nothing about the API key: the key is held
  only by the worker, so the web process cannot observe it;
- a worker tile derived from batch evidence in the database. **Working** means an
  active batch is heartbeating, **Stalled** means an active batch has not renewed
  its lease for two lease periods (what a hung worker looks like from the web
  tier), and **Needs recovery** counts batches awaiting manual intervention.
  **Idle** means no batch is active; because the worker writes only while it holds
  work, that is not evidence the process is running;
- run key, allowed model, and an optional **Pilot size**. Leaving Pilot size blank
  queues the complete ready selection under one run key. Entering a value creates a
  smaller record-ID-ordered trial without changing the meaning of the selection;
- the resulting job count and estimated provider-batch count. Runs at or above the
  configured large-run threshold require the reviewer to type the exact job count,
  and the server enforces a separate emergency per-run ceiling;
- the per-schedule output-token ceiling, worker batch size, selection order, skip
  behavior, and the selected model's frozen Batch rates.

The confirmation page deliberately makes no provider request: the web tier has no
API key, and image-dependent input usage cannot be known exactly before the worker
builds the request. Exact encoded request bytes are calculated, bounded, and
recorded by the worker after it reads each image. When at least three priced
successes exist for the selected model, the page extrapolates a clearly labeled
historical planning estimate; the reviewer usage report remains the source for
actual provider usage and derived cost after processing.

Confirmation only creates the immutable run and queued jobs. It does not make a
provider request from the web process. The worker automatically claims the run in
chunks of `CLAUDE_TRANSCRIPTION_BATCH_SIZE`, so a 2,000-schedule campaign keeps one
run key while producing as many provider batches as needed. Run, batch, and job
admin pages expose progress, errors, and token usage. Reviewers may cancel only jobs
that are still locally queued and have not been claimed into a batch; submitted and
evidence-bearing jobs remain protected.

A successful candidate never changes the canonical `transcription_status` by
itself. Reviewers reach those schedules through **Project Management → AI
Transcriptions - Ready for Review**, which applies the `AI transcribed` schedule
filter and opens the read-only comparison workflow. The ordinary Review Queue
continues to mean canonical human/imported work. The admin Overview reports human
review readiness, AI candidate readiness, approvals, and approval percentage as
separate measures; only `approved` schedules count toward project approval.

## Usage, cost, and benchmark reporting

Reviewers can open **AI Transcription → Usage & Costs** from the always-expanded
admin sidebar. The admin home also shows a compact cost summary. Reporting includes
run/job counts, success and failure counts, success rate, total/mean/median/P95 token
usage, elapsed throughput, estimated cost, cost per successful transcription, and
per-run model/contract/pricing provenance. CSV and JSON exports provide one row per
job for reproducible outside analysis. A dependency-free horizontal chart compares
cost per successful transcription across the ten most recent priced runs, with model
labels and the underlying totals retained as text.

Costs are derived with `Decimal` arithmetic from the untouched provider usage and
the rates frozen on that job's run. Cache categories are priced separately when the
provider supplies their breakdown. Failed jobs remain in usage and cost totals.
Jobs from older runs without a valid snapshot remain in token totals and exports but
are excluded from cost totals with a visible warning. These estimates are not an
Anthropic invoice; organization-level billing reconciliation belongs in financial
operations, not immutable transcription evidence.

As a calculator sanity check, the pre-reporting local test runs recorded 37,079
input tokens and 4,201 output tokens with no cache usage. Applying Claude Sonnet 4.6
Batch rates retrospectively gives `$0.087126`, consistent with the approximately
`$0.09` observed provider cost. The dashboard still labels those historical runs
unpriced because their rates were not frozen at launch; this comparison validates
the formula without rewriting provenance.

Efficiency and transcription quality are deliberately separate. Before a contract
or model is approved for a large run:

1. Freeze a stratified human gold sample covering clear, blank-heavy, zero-heavy,
   difficult handwriting, repeated entities, and varied geography/denominations.
2. Queue every candidate model/contract against the same schedule IDs. Never edit
   old runs or reuse a run key.
3. Export usage and compare efficiency metrics: success/failure rate, input/output
   distributions, elapsed throughput, total estimated cost, and cost per success.
4. Independently review quality against the image and frozen human snapshot:
   schema validity, field completeness, exact numeric agreement, normalized text
   agreement, blank-versus-zero errors, entity alignment, uncertainty notes, and
   reviewer correction time.
5. Record efficiency and quality findings side by side, but do not collapse them
   into one score. A cheaper run is not better if accuracy or review burden worsens.
6. Approve expansion only after every pilot job is accounted for, failures are
   explained, quality thresholds are met, and projected scale fits the budget.

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

At `INFO` level, the worker records three operational lifecycle events: a local
batch claiming queued jobs, successful submission with the provider batch ID and
encoded request size, and each returned job result with terminal state and token
counts. These entries include run, batch, opaque job, and schedule identifiers for
correlation. They never include API credentials, image data, prompts, raw provider
responses, or transcription content.

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

### Revising the prompt or schema

Treat every prompt/schema version as a permanent scholarly contract. Do not reuse a
version name for changed instructions or a changed candidate shape, even though old
runs retain exact copies of their original contract.

To introduce a new contract:

1. Copy the current prompt and schema to files with a new matching version name,
   such as `relec-1926-v2.md` and `relec-1926-v2.json`. Keep the older files in the
   repository for review and reproducibility.
2. Update `CONTRACT_VERSION` in `census/transcription/contracts.py` to the new name.
   Update the schema `$id`, its top-level `schema_version` constant, and the prompt's
   required output version together.
3. Add or revise fixtures and tests for every semantic change. Confirm the original
   candidate schema still enforces research constraints locally and the derived
   transport schema contains only features supported by Anthropic structured output.
4. Run the transcription tests, the full test suite, and `manage.py check` before
   making a live request.
5. Launch a new, uniquely named run for the pilot. Never retrofit the new contract
   into an existing run or overwrite a failed run; exact prompt/schema contents and
   hashes are frozen when each run is created.
6. Compare the pilot candidates with human snapshots in admin and record findings
   before approving the new contract for a larger batch.

A contract change does not require a database migration unless the durable run,
batch, job, or output models also change.

## Representative pilot runbook

Live API calls incur cost and require explicit authorization. Start with a bounded
sample rather than selecting a convenient sequence of similar schedules. Include,
when available:

- a clear, substantially complete schedule;
- a schedule with meaningful blanks and zeroes;
- faint, corrected, crossed-out, or otherwise uncertain handwriting;
- multiple religious bodies, memberships, or clergy;
- different denominations and geographic contexts;
- variation in image dimensions or file size.

Before queueing the pilot:

1. Confirm the model allowlist, object-storage settings, and transcription feature
   flag are configured, and that the API key is present in the worker's environment
   (check the worker's logs, not the admin, which cannot see it).
2. Confirm every selected schedule has a working `original_image` reference. Use the
   manifest import dry run and bounded storage verification when local references are
   incomplete.
3. Restart the Django development server after environment changes. Stop and restart
   the worker after code or contract changes because the management-command process
   does not auto-reload.
4. In the Census Schedule changelist, select the representative sample, choose the
   Claude queue action, give the run a unique key, and use **Pilot size** only if the
   selected set is broader than the intended sample.
5. Start `run_transcription_worker` separately. Monitor the read-only Runs, Batches,
   and Jobs pages until every request reaches a terminal or manual-recovery state.

Review each successful candidate through **Compare transcriptions** with the image
visible. Record at least schema validity, blank-versus-zero differences, numeric
agreement, significant text differences, newly recovered fields, uncertainty notes,
input/output token usage, and reviewer observations. Do not promote values during
this review.

Keep provider rejections and invalid results as evidence. After correcting code or a
contract, create a new immutable run rather than editing or resubmitting the failed
one. Do not automatically retry `needs_recovery` work until provider acceptance is
resolved; doing so can duplicate paid requests.

Do not expand the batch until all pilot jobs are accounted for, differences have
been reviewed, unexpected failures have an explanation, and observed usage remains
within the approved budget. When the pilot is complete, stop the worker with
`Ctrl-C`; queued and provider-backed state remains in PostgreSQL for a later restart.

### Representative pilot completed

Run `claude-pilot-20260810-representative` evaluated contract
`relec-1926-v1` with `claude-sonnet-4-6` at application revision
`e23c41ca54a27b9c81df0ba0bf7c07a93f7eabf6`. It deliberately included a
zero-heavy schedule with clergy, a second zero-heavy schedule from a different
geographic context, and a blank-heavy schedule without denomination context.

| Resource | Result | Input tokens | Output tokens |
| --- | --- | ---: | ---: |
| `6875` | Succeeded | 7,653 | 852 |
| `32765` | Succeeded | 7,291 | 761 |
| `182638` | Succeeded | 6,344 | 883 |

The single provider batch ended normally with all three requests accounted for. It
contained 15,146,239 encoded bytes and used 21,288 input and 2,496 output tokens;
the provider reported no cache-creation or cache-read tokens. A reviewer visually
compared all three immutable candidates with their human snapshots and source
images. The materials were acceptable, with no blocking prompt/schema issue or
required `relec-1926-v2` revision identified before merge. This review did not
promote any candidate values into canonical census models.

## Issue scope reconciliation

- #64's durable candidate-generation scope is implemented: immutable provenance and
  outputs, batches and jobs, environment-only credentials, request byte limits,
  restart and recovery behavior, raw failures, validation, usage capture, reviewer
  admin pages, worker deployment, tests, and operations documentation. The remaining
  acceptance step is a separately authorized pilot across several representative
  schedule types; resource `6893` proves the bounded single-schedule path only.
- #142's versioned prompt/schema, location contract, semantic validation, hashes,
  fixtures, mocked request tests, and revision procedure are implemented. Evaluation
  against the multi-schedule representative sample remains pending and must use a new
  contract version if it exposes changes to the prompt or schema.
- #127's durable usage/cost reporting, immutable validated pricing, reviewer
  dashboard, reproducible exports, and benchmark protocol are implemented. Quality
  remains a separate human evaluation against frozen snapshots; estimated costs are
  intentionally based on completed provider usage rather than a web-tier preflight.
- #134 still owns reconciliation and promotion. The comparison page in this change
  is intentionally read-only and records no decisions or canonical-model updates.
- #143 still owns crawler-query and thumbnail performance work. The manifest commands
  here only link schedule records to existing object-storage originals for
  transcription; they do not warm thumbnails or alter the public browser.

## Testing

Tests use fake clients and local media storage. They make no live Anthropic or S3
requests. Covered behavior includes contract validation, payload construction,
selection-driven runs, active-work exclusion, intentional retranscription, pilot
sizing, large-run confirmation, auto-chunking, out-of-order results, usage
aggregation, provider-evidence immutability, ambiguous submissions, stale submission
leases, and protected raw outputs.

Provider references: [Message Batches API](https://platform.claude.com/docs/en/api/messages/batches/create)
and [Structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs).
