# AI Transcription Write-Back API — Design

**Date:** 2026-07-06
**Status:** Approved (pending spec review)
**Branch:** `refactor/transcription-and-api`

## Problem

We want to transcribe historical census schedule images at scale (~250,000
records) using the Claude API, and write the structured results back into the
Django data model. An external orchestrator will pull a schedule image, call the
Claude API (via the Batch API) to produce structured JSON, and `POST` that JSON
to Django. This spec defines the write path: the endpoint, its authentication,
the data-preservation guarantee, and the overwrite semantics.

The existing API (`census/api_views.py`) is entirely read-only
(`ReadOnlyModelViewSet`) and public (`AllowAny`). There is no authenticated
write path today — this feature adds one, narrowly scoped.

## Why "outside Django"

Transcription orchestration runs **outside** the Django process (a standalone
script / Claude Batch API loop on its own infrastructure), so results arrive
over HTTP rather than through direct ORM access. This keeps transcription
decoupled from the web deployment. Record volume alone would not force this
choice, but decoupling the batch workload does.

## Existing assets this builds on

- `CensusSchedule.ai_transcription` (JSONField) — raw AI response, stored as-is.
- `CensusSchedule.human_transcription` (JSONField) — frozen snapshot of the
  original human-transcribed data, for comparison and recovery.
- `census/management/commands/snapshot_human_transcription.py` — its
  `serialize_schedule()` function flattens a `CensusSchedule` plus its
  `ReligiousBody` → `Membership` and `Clergy` relations into JSON. This shape is
  reused as the **wire contract** for the write endpoint. The command is
  idempotent (default: only fills records where `human_transcription` is null;
  `--overwrite` forces re-snapshot; `--dry-run` reports counts).

## Design

### Transport & authentication

- A new **authenticated write endpoint**, separate from the public read-only
  API. The endpoint sets its own `permission_classes` to require an
  authenticated user (the global default remains `AllowAny` for reads).
- **DRF `TokenAuthentication`** backed by a dedicated **`claude` service-account
  Django user**. One token, sent as `Authorization: Token <token>`. This user
  doubles as the auth credential and the attribution identity in admin history.
  Requires adding `rest_framework.authtoken` to `INSTALLED_APPS` and running its
  migration.
- Rationale for token-per-user over a static API-key package: it directly
  answers "should there be a `claude` user?" — yes — and gives attribution for
  free, fitting the existing transcriber/reviewer workflow.

### Endpoint

```
POST /api/census/schedules/{pk}/ai-transcription/
Authorization: Token <token>
Content-Type: application/json

<serialize_schedule()-shaped JSON payload>
```

- **Addressing key:** the record **PK**. The orchestrator already knows the PK
  from pulling the image; `schedule_id` off the form face is not guaranteed
  unique and is not used for addressing.
- **Wire contract:** the same nested shape `serialize_schedule()` produces —
  `schedule_fields`, `religious_bodies[]` (each with nested `membership[]`), and
  `clergy[]`. Incoming row `id`s are ignored (rows are regenerated on
  replace-all). This is the shape Claude is instructed to emit.

### Write sequence (one DB transaction per POST)

1. **Guard.** If the target record's `human_transcription` is null, reject with
   `409 Conflict`. The human baseline must already be frozen before AI is
   allowed to overwrite live fields. The endpoint does **not** perform the
   snapshot itself; it only refuses to proceed without one.
2. **Store.** Save the raw request JSON verbatim to `ai_transcription`.
3. **Replace-all overwrite.** Validate the payload with a DRF serializer, then:
   - Assign the `CensusSchedule` scalar fields covered by `serialize_schedule()`.
   - Delete the schedule's existing `ReligiousBody` / `Membership` / `Clergy`
     rows and recreate them from the payload.
4. **Flip status.** Set `transcription_status = "needs_review"`.

Replace-all is safe because the human baseline is frozen in
`human_transcription` (step 1 guarantees it) and a full DB backup is taken
before any transcription run.

### Field scope

The overwrite touches exactly the fields `serialize_schedule()` serializes —
schedule scalars (`schedule_title`, `box`, `notes`, `num_assistant_pastors`,
respondent fields, `district_stamp`, `denomination_code_stamp`, `marginalia`,
`date_received`), `schedule_denomination`, and the `ReligiousBody` / `Membership`
/ `Clergy` relations. Fields **not** in that snapshot — geographic FKs (`county`,
`populated_place`), project-management fields (`assigned_transcriber`,
`assigned_reviewer`, `transcription_notes`), and DataScribe/Omeka reference
fields — are **out of scope** and left untouched. This keeps the write path
symmetric with the snapshot and avoids the AI clobbering assignment/location
data it has no basis to set.

### Denomination FK resolution

The AI cannot know internal denomination PKs, so denomination arrives as a
**code/name string**. The endpoint attempts to resolve it to a `Denomination`
FK (`schedule_denomination`, and `ReligiousBody.denomination`); on no match it
**leaves the FK null for the reviewer** rather than guessing. The raw string is
preserved in `ai_transcription` regardless.

### Validation & atomicity

- A DRF serializer validates payload structure and types before any DB write; a
  malformed AI payload is rejected (`400`) without touching the record.
- The entire sequence runs inside `transaction.atomic()`. Any failure rolls back
  — no partial overwrite, no orphaned relation rows.

## Operational preconditions

- Run `snapshot_human_transcription` once over the corpus before starting
  transcription; re-run before any later batch (idempotent — only fills nulls)
  so records added after the initial snapshot also get a frozen baseline. Safe
  operational order is always **snapshot → then AI batch**.
- Take a full database backup before starting a transcription run.

## Out of scope

- The orchestrator itself (image retrieval, Claude Batch API calls, retry/queue
  handling) — it is an external client of this endpoint.
- Model/prompt selection and cost tuning for the transcription calls.
- Review UI changes — records simply land in the existing `needs_review` state
  and flow through the current workflow.
- Any change to the public read-only API surface.

## Cost context (informational)

Rough batch-API estimate for 250k single-image transcriptions, assuming
~3,500 input tokens (instructions + schema + image) and ~1,200 output tokens per
image, Batch API at 50% off: roughly **$1–6k** for the corpus depending on model
(≈$1.2k Haiku 4.5, ≈$2.4–3.6k Sonnet 5, ≈$5.9k Opus 4.8). Output length, image
resolution, and model tier are the dominant levers. Calibrate with a pilot of
~50–100 representative schedules, reading back real `response.usage` before
committing to a full run.
