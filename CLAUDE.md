# Religious Ecologies Project - Claude Code Session Notes

> For full technical documentation see [AGENTS.md](./AGENTS.md). For feature specs and domain rules see [SPEC.md](./SPEC.md).

## Project Overview
Django project for managing historical religious census data transcription with undergraduate/graduate student workers.

---

## Implemented Features

### Project Management System
- **Status Workflow**: `unassigned` → `assigned` → `in_progress` → `needs_review` → `completed` → `approved`
- **User Assignments**: `assigned_transcriber` and `assigned_reviewer` fields on `CensusSchedule`
- **Auto-status Logic**: Records auto-transition from `unassigned` → `assigned` when a transcriber is set
- **Permissions**: Transcribers (students) can add/edit but not delete; Reviewers (PIs) have full access; Transcribers see only their assigned records

### Django-Unfold Admin
- Custom dashboard (`templates/admin/index.html`) with metrics, charts, activity feed
- Organized sidebar: Dashboard, Analytics, Transcriptions, Location Data, Content Management, System Admin
- Religious Ecologies blue theme (`#0060b1`) via `static/css/custom_unfold.css`
- Dashboard context injected via `religious_ecologies/admin.py`

### Bulk Assignment System
- Multi-record selection → assign transcriber + reviewer + status in one operation
- Quick actions: "Assign to me," remove transcriber/reviewer
- Data quality tools: Schedule ID gap analysis, missing county analysis
- Templates: `templates/admin/census/bulk_assign.html`, `schedule_gap_analysis.html`, `missing_county_analysis.html`

### Smart Admin Filtering
- Students see only records where `assigned_transcriber = current_user`
- PIs see all records
- Workflow filters, assignment status filters, location filters

---

## Commands

```bash
# Preferred: uv (poetry also works)
uv run python manage.py migrate
uv run python manage.py makemigrations census
uv run python manage.py setup_transcription_groups
uv run python manage.py check
uv run python manage.py generate_thumbnails   # Backfill thumbnail aliases (idempotent)
```

Setup for new deployments:
1. Run migrations
2. Run `setup_transcription_groups`
3. Add users to "Transcribers" and "Reviewers" groups via Django admin
4. Run `generate_thumbnails` to backfill image thumbnails (new uploads are covered automatically by the `saved_file` signal)

## Thumbnails

Thumbnails are **never generated during a request**. Public templates use the
`{% existing_thumbnail_url %}` tag (`census/templatetags/census_thumbnails.py`),
which only looks up already-generated thumbnails via easy-thumbnails' cache
tables. Generation happens at upload time (`saved_file` signal connected in
`census/apps.py`) and in bulk via `manage.py generate_thumbnails`.

---

## Django Debug Toolbar

Enabled conditionally when `DEBUG=True` in `config/settings.py`. The toolbar and its middleware are only added to `INSTALLED_APPS` and `MIDDLEWARE` in debug mode. URLs are registered at `__debug__/` in `config/urls.py`, also gated on `DEBUG`.

---

## Interactive Visualizations with Observable Plot

### Current Approach (Simplified)
Each visualization has a **wrapper script** with the target div ID hardcoded as a constant. No global state, no params resolution, no data URLs — just straightforward ES6 modules.

```javascript
// Example: static/viz/denominational-diversity-wrapper.js
import * as Plot from "@observablehq/plot";
import { data } from "./denominational-diversity-data.js";

const TARGET_DIV = "denominational-diversity";
const plot = Plot.plot({ ... });
document.getElementById(TARGET_DIV).appendChild(plot);
```

Import maps in `templates/pages/blog_detail.html` resolve `@observablehq/plot` (0.6) and `d3` (v7) from jsDelivr CDN — no bundler needed.

**Adding new visualizations:** See `docs/INTERACTIVE_VISUALIZATIONS.md`.

**Commands:**
```bash
uv run python manage.py fix_interactive_viz      # Update existing posts
uv run python manage.py convert_hugo_shortcodes  # Convert new Hugo posts
```

---

## Key File Locations

```
census/
  models.py                          — CensusSchedule with workflow fields
  admin.py                           — Bulk actions, filters, custom views
  management/commands/
    setup_transcription_groups.py    — Creates Transcribers/Reviewers groups
config/settings.py                   — UNFOLD config, DB, auth, storage
templates/admin/
  index.html                         — Custom dashboard
  census/
    bulk_assign.html                 — Bulk assignment interface
    schedule_gap_analysis.html       — Gap analysis tool
    missing_county_analysis.html     — County analysis tool
static/css/custom_unfold.css         — Religious Ecologies blue theme
religious_ecologies/
  admin.py                           — Dashboard context injection
  apps.py                            — AppConfig
DEVNOTES.md                          — User permission documentation
docs/INTERACTIVE_VISUALIZATIONS.md  — Guide for adding Observable Plot vizzes
```
