# Background Run Publishing — Design

**Date:** 2026-10-07
**Status:** Approved
**Issue:** #168 (decision comment of 2026-10-06)
**Branch:** `feat/publish-run`

## Problem

Reviewers publish one agent transcription run over a selection of schedules.
Runs are planned per denomination family, so a single publish can cover 20,000+
schedules (e.g. Methodists). Classifying and applying that many schedules
inside a web request is impossible: each schedule needs several queries to
classify and a full reconciliation to apply, and production already returns
502s on slow requests.

## Publishing rules (unchanged from #168)

For the chosen run, each schedule falls into exactly one case:

| Case | Detection | Result |
|---|---|---|
| Reconciled | A standing reconciliation used this run's output in any way, or came after it | Keep; approve if Ready for Review |
| Edited | Current data differs from what the latest standing agent-applying reconciliation produced (shared fields only, `schema_version` ignored) | Keep; approve if Ready for Review |
| Promote | Everything else, including earlier student transcription | Promote the run's output and approve |
| No output | The run has no output for the schedule | Skip |

Promote-case schedules saved by a person after the run's output arrived are
counted as an overwrite warning; they are not protected.

## Design

### Two steps, both in the background

1. **Preview.** The reviewer selects schedules and a run in the admin action and
   starts a preview. This creates a `RunPublication` (state `previewing`) and one
   `RunPublicationItem` per selected schedule. The worker classifies items in
   chunks. When all items are classified, the state becomes `ready`.
2. **Publish.** On the status page the reviewer reviews the counts, adds notes,
   confirms, and the state becomes `publishing`. The worker applies items in
   chunks, re-classifying each schedule at that moment so changes since the
   preview are respected. When all items have an outcome, the state becomes
   `completed`.

A publication can be canceled while `previewing`, `ready`, or `publishing`;
unprocessed items keep no outcome.

### Models

- `RunPublication`: run, requested_by, confirmed_by, notes, state, created_at,
  confirmed_at, finished_at.
- `RunPublicationItem`: publication, schedule (unique together), case,
  overwrite_warning, outcome (`published`, `approved`, `kept`, `skipped`,
  `failed`), detail (skip or failure reason).

### Worker

Publishing lives in `census/transcription/publishing.py` with its own
`run_once()`, separate from `ClaudeTranscriptionWorker`. The existing
`run_transcription_worker` loop calls both; either doing work skips the poll
sleep, so chunks run back to back. Publishing runs even when Claude
transcription is disabled (with `--idle-when-disabled`). An error in one item
marks that item `failed` and never stops the loop. Chunks of 200 items keep
each iteration well under the 10-minute liveness window.

Assumes one worker process (production runs one replica). Re-processing an item
after a crash is safe: classification is idempotent, and a re-applied publish
finds its own reconciliation and keeps the data.

### Admin

- **Publish a transcription run** action: run picker plus selected count;
  submitting starts the preview and redirects to the status page.
- **Run publications** admin (reviewers only): list of publications and a status
  page with progress, per-case and per-outcome counts, the overwrite warning,
  failed items, confirm and cancel controls, and auto-refresh while the worker
  is busy.
- **Transcription run** filter on the schedule list, so a reviewer can select
  every schedule a run covers (with select-all across pages).

## Out of scope

- Notifications beyond the status page.
- Field-level merging (rejected in #168).
- Multiple publishing workers.
