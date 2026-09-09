# SPEC.md

> For technical implementation details, architecture, and developer documentation, see [AGENTS.md](./AGENTS.md).

---

## Table of Contents

- [Overview](#overview)
- [Users & Roles](#users--roles)
- [Business Rules](#business-rules)
- [Features](#features)
- [User Flows](#user-flows)
  - [Flow 1: Transcribing a Census Schedule](#flow-1-transcribing-a-census-schedule)
  - [Flow 2: Reviewing and Approving Transcriptions](#flow-2-reviewing-and-approving-transcriptions)
  - [Flow 3: Bulk Assigning Records](#flow-3-bulk-assigning-records)
  - [Flow 4: Browsing Census Data (Public)](#flow-4-browsing-census-data-public)
- [Out of Scope](#out-of-scope)
- [Open Questions](#open-questions)

---

## Overview

**Religious Ecologies** is a web platform for digitizing and publishing the 1926 Federal Census of Religious Bodies. The census captured detailed statistics on American churches — membership counts, clergy information, property values, and school enrollments — at the congregation level. This project makes that data searchable, analyzable, and publicly accessible.

**Problem it solves:** The original census schedules exist as scanned images in Omeka. Without a structured transcription workflow, the data cannot be queried, mapped, or used for historical analysis.

**Core value proposition:**
1. A managed transcription pipeline that assigns student workers to specific records and tracks progress through review and approval
2. A clean, structured dataset exposed via REST API and interactive public visualizations
3. A scholarly publication platform (blog + visualizations) for communicating findings

**Target audiences:**
- **Research team** (PIs, postdocs, students) at RRCHNM: primary users of the admin/transcription system
- **Historians and researchers**: Access data via the public browser and API
- **General public**: Explore interactive maps and read scholarly blog posts

**Success metrics:**
- Percentage of census schedules with `transcription_status = approved`
- Number of `ReligiousBody` records with geocoded coordinates
- Public API usage and data downloads

---

## Users & Roles

### Principal Investigators / Reviewers

Full access to the system. Responsible for project oversight, data quality, and scholarly output.

**Can:**
- View all census schedules regardless of assignment
- Assign records to transcribers and reviewers
- Bulk-assign records by denomination, location, or status
- Edit any record at any status
- Approve finalized transcriptions (`approved` status)
- Access all admin tools: gap analysis, missing county analysis, export
- Create and publish blog posts, pages, and visualizations
- Manage user accounts and group memberships

**Cannot:**
- Delete records without superuser access (extra protection against accidental data loss)

**Typical persona:** History faculty, postdoctoral researcher, project manager

---

### Transcribers

Student workers (undergraduate or graduate) assigned specific records for data entry.

**Can:**
- View only their assigned census schedules
- Enter transcription data: ReligiousBody details, Membership statistics, Clergy information
- Mark records as needing review when finished
- Add transcription notes

**Cannot:**
- See records assigned to other transcribers
- Assign records to themselves or others
- Delete records
- Access data quality tools or export functions
- Approve records

**Typical persona:** Undergraduate research assistant, graduate student

---

### Public Users (Unauthenticated)

Anyone accessing the public-facing website.

**Can:**
- Browse census records by state, county, and populated place
- View individual census record details
- Explore interactive maps (denomination distribution, demographics, urban congregations)
- Use the REST API to query records
- Read blog posts and scholarly visualizations
- Browse denomination and location indexes

**Cannot:**
- Access the admin interface
- Modify any data
- See records that haven't been transcribed

---

### Superusers

IT/infrastructure administrators with full Django admin access.

**Can:** Everything, including user management, permission changes, and destructive operations.

---

### Permission Matrix

| Action | Superuser | Reviewer | Transcriber | Public |
|--------|-----------|----------|-------------|--------|
| View all records | ✓ | ✓ | Own only | Published only |
| Transcribe records | ✓ | ✓ | Assigned only | ✗ |
| Assign records | ✓ | ✓ | ✗ | ✗ |
| Approve records | ✓ | ✓ | ✗ | ✗ |
| Delete records | ✓ | ✗ | ✗ | ✗ |
| Bulk assignment tools | ✓ | ✓ | ✗ | ✗ |
| Data quality tools | ✓ | ✓ | ✗ | ✗ |
| Export data | ✓ | ✓ | ✗ | API only |
| Manage users/groups | ✓ | ✗ | ✗ | ✗ |
| Publish blog/pages | ✓ | ✓ | ✗ | ✗ |

---

## Business Rules

### Transcription Workflow

- Student transcription follows:
  `unassigned → assigned → in_progress → completed → approved`
- Imported records default to `needs_review`; already approved imports remain `approved`
- Both `needs_review` and `completed` appear in the PI/editor review queue
- Status can be set backward by Reviewers (e.g., returning a record to `in_progress`)
- A schedule is **automatically** moved from `unassigned` to `assigned` when a transcriber is assigned
- Transcribers submit finished work as `completed`; only Reviewers can set `approved`, through the schedule-level reconciliation workflow
- Reconciliation compares any two distinct sources: live canonical data, immutable human snapshots, or immutable agent outputs. The baseline defaults to the newest human snapshot (or canonical when none exists), while the comparison defaults to the newest agent output.
- Mixed reconciliations record both evidence sources plus every field and related-row source decision as append-only provenance; repeated entities are matched by stable identity or unique signatures, never silently by list order
- Reviewers may bulk-promote selected schedules from the admin action menu. Each schedule uses the output belonging to its newest agent run, is validated independently, and receives its own reconciliation event; schedules without valid model evidence are skipped.
- Reviewers may restore selected schedules to the data state before their newest unreversed reconciliation. A restore never deletes history: it creates a new append-only reconciliation linked through `reverses`, marks prior evidence as superseded, and leaves the restored schedule approved.
- A schedule must have at least one `ReligiousBody` record before it can be marked `completed` or `needs_review`

### Location Hierarchy

- All geographic data follows the strict hierarchy: `State → County → PopulatedPlace`
- A `CensusSchedule` may have a `county` without a `populated_place` (county-level only) but not vice versa
- A `PopulatedPlace` must belong to a `County`; a `County` must belong to a `State`
- Location data on `ReligiousBody` (latitude/longitude) is derived from geocoding the congregation's address — it is not the same as the schedule's `populated_place`

### Geocoding Rules

- `ReligiousBody.geocode_status` values: `pending`, `success`, `failed`, `skipped`
- Geocoding is not automatic; it is triggered by a management command or admin action
- Records with `geocode_status = success` are eligible for display on public maps

### Record Visibility

- Transcribers see only records where `assigned_transcriber = current_user`
- Reviewers and superusers see all records
- Public-facing views show only records with sufficient data (at least one linked `ReligiousBody`)

### Data Integrity

- Deleting a `CensusSchedule` cascades to delete all linked `ReligiousBody`, `Membership`, and `Clergy` records
- `Denomination`, `State`, `County`, and `PopulatedPlace` records use `PROTECT` on foreign keys — they cannot be deleted while referenced
- All major model changes are tracked via `django-simple-history`; a full audit trail is maintained

### Import Rules

- The data import pipeline must be run in order:
  1. Import denominations
  2. Import locations (populated places)
  3. Import census schedules (DataScribe data)
  4. Import image paths
  5. Fetch images from Omeka
  6. Link counties from Omeka metadata
- Re-running imports is safe; records are matched by stable identifiers (`denomination_id`, `resource_id`, `ahcb_id`)

---

## Features

### Feature: Transcription Admin Interface

**Description:**
A customized Django admin interface (using Django Unfold) tailored for the transcription workflow. The primary workspace for all research team members.

**User Value:**
Provides a professional, organized interface for managing the transcription project without requiring custom application development.

**Functionality:**
- Dashboard with key metrics: total records, transcribed count, completion percentage, recent activity
- Organized sidebar navigation with 6 sections: Dashboard, Analytics, Transcriptions, Location Data, Content Management, System Admin
- Census schedule list with smart filtering by status, assignment, denomination, location
- Transcribers see only their assigned records; Reviewers see all
- Inline editing of `ReligiousBody`, `Membership`, and `Clergy` records within a schedule
- Bulk actions: mark records as various statuses, assign/unassign transcribers
- Change history visible for all records

**User Interactions:**
- Admin user logs in → sees dashboard with progress metrics
- Transcriber selects a record → edits fields inline → marks it "ready for review"
- Reviewer opens the review queue → approves or returns records with notes
- PI views dashboard → monitors team progress

**Success Criteria:**
- Transcribers can complete a record without PI assistance
- Reviewers can make an audited schedule-level approval decision without changing immutable transcription evidence
- Dashboard accurately reflects real-time project status

---

### Feature: Bulk Assignment System

**Description:**
A dedicated admin interface for efficiently assigning multiple census schedules to transcribers and reviewers at once.

**User Value:**
Eliminates the tedious work of assigning records one by one at the start of each work session.

**Functionality:**
- Multi-select records from the admin list view using Django's built-in checkbox selection
- Bulk assignment form shows a list of all Transcribers and Reviewers with checkboxes
- Simultaneously assign a transcriber, assign a reviewer, and set a target status in one operation
- Quick actions: "Assign to me," "Remove transcriber," "Remove reviewer"
- Confirmation screen shows how many records will be affected before committing
- Filter records before bulk assignment by state, county, denomination, or current status

**Edge Cases:**
- Records already assigned to someone: Show warning, allow override or skip
- No users in Transcribers group: Show error with link to user management

---

### Feature: Data Quality Tools

**Description:**
Admin-only analysis tools for identifying gaps and inconsistencies in the census schedule data.

**User Value:**
Helps PIs identify data problems before they affect analysis or publication.

**Functionality:**

**Schedule ID Gap Analysis:**
- Lists gaps in the sequential `schedule_id` numbering
- Helps identify missing or unimported schedules
- Exportable as CSV

**Missing County Analysis:**
- Lists schedules that have no linked county or populated place
- Groups by count to prioritize cleanup effort
- Shows denomination distribution of un-located records

**Success Criteria:**
- Tool runs in under 10 seconds for full dataset
- Results accurately reflect current database state

---

### Feature: Census Browser (Public)

**Description:**
A public-facing interface for browsing the transcribed census data by geography.

**User Value:**
Allows historians and the general public to explore the data without needing API knowledge.

**Functionality:**
- Cascading dropdown filters: State → County → Populated Place
- Results list shows denomination, location, membership totals
- Links to individual record detail pages
- Pagination for large result sets
- URL structure supports direct linking (e.g., `/census/browser/NY/Kings/`)

**User Interactions:**
- User selects a state → county dropdown populates → place dropdown populates → records list updates
- User clicks a record → navigates to full detail page with all transcribed fields
- User bookmarks a filtered URL → lands on same filtered view

**Edge Cases:**
- State with no transcribed records: Shows empty state message
- Very large county (e.g., Cook County, IL): Paginated results with count shown

---

### Feature: Interactive Maps

**Description:**
Leaflet.js-based maps showing congregation density, denomination distribution, and demographic patterns.

**User Value:**
Spatial visualization reveals geographic patterns invisible in tabular data.

**Functionality:**

**Denomination Distribution Map** (`/census/map/`):
- Choropleth map of denominations by county
- Color-coded by denomination family
- Clickable counties with popup showing top denominations and member counts

**Demographics Map** (`/census/demographics-map/`):
- Member counts by geography
- Toggle between raw counts and per-capita rates

**Urban Congregations Map** (`/census/viz/urban-congregations/`):
- Congregation-level point markers in major cities
- Filterable by denomination family
- Popup shows congregation name, denomination, membership

**Data Source:**
- All maps load data from the DRF REST API (`/census/api/`)
- GeoJSON endpoints for county-level choropleth data

**Success Criteria:**
- Maps load within 3 seconds on average connection
- All congregations with `geocode_status = success` appear as markers
- Maps are usable on mobile (touch zoom, responsive layout)

---

### Feature: REST API

**Description:**
A publicly accessible read-only REST API exposing the transcribed census data in structured JSON format.

**User Value:**
Allows researchers to download and analyze the data programmatically without web scraping.

**Functionality:**
- `GET /census/api/religious-bodies/` — paginated list of all congregations
- `GET /census/api/religious-bodies/<id>/` — single congregation detail
- `GET /census/api/denominations/` — denomination reference list
- Filtering by denomination, county, populated place, geocode status
- Full-text search on name fields
- Ordering support
- 100 records per page; standard `next`/`previous` pagination links

**Edge Cases:**
- Request for non-existent record: 404 with JSON error
- Invalid filter parameter: Ignored (Django Filter behavior)

---

### Feature: Content Management (Blog & Visualizations)

**Description:**
A CMS for publishing scholarly blog posts, static pages, and featured interactive visualizations.

**User Value:**
Provides a publication venue for the research team's findings, co-located with the data.

**Functionality:**

**Blog Posts:**
- Markdown content with image support
- Author attribution, publication date
- Thumbnail image for listing pages
- Draft mode (hidden from public until published)
- Support for embedded Observable Plot interactive visualizations (via ES6 import maps)

**Static Pages:**
- Markdown + HTML content
- Optional navigation inclusion with custom label and sort order
- Scheduled publishing via `publish_date`

**Visualizations:**
- Featured interactive D3/Observable Plot visualizations
- Associated JavaScript and CSS files
- DOI field for scholarly citation

**User Interactions:**
- Reviewer logs into admin → creates blog post → sets `is_draft=False` → post appears on `/blog/`
- User visits `/blog/` → sees list of published posts → clicks through to detail
- Detail page loads Observable Plot visualizations via CDN import maps (no page reload)

---

### Feature: Analytics Dashboard

**Description:**
An internal reporting interface for the research team to query and analyze the transcribed data.

**User Value:**
Enables the team to answer research questions about the dataset without writing SQL.

**Functionality:**
- Query builder for filtering records by multiple criteria simultaneously
- Denomination analysis: membership statistics by denomination family
- Location analysis: record and membership distribution by state/county
- Data completeness report: which fields are missing across what percentage of records
- Missing place IDs report: schedules that cannot be geo-located

**Current Status:** Views are implemented; expanding as analysis needs grow.

---

## User Flows

### Flow 1: Transcribing a Census Schedule

**Goal:** Student worker completes transcription of an assigned census schedule

**Starting Point:** Transcriber logs into `/admin/`

**Steps:**
1. Transcriber sees the admin dashboard → sidebar shows "Transcriptions" section
2. Clicks "Census Schedules" → list view auto-filters to show only assigned records
3. Selects a record with status `assigned` or `in_progress`
4. Record detail page opens, showing the original census schedule image
5. Transcriber fills in `ReligiousBody` inline form: name, denomination, address, membership counts, property values, clergy information
6. Saves record → status auto-transitions to `in_progress` (if still `assigned`)
7. When finished, transcriber clicks "Mark as Ready for Review"
8. Record status becomes `completed`; transcriber can no longer edit it

**Success Outcome:**
Record has `transcription_status = completed` and at least one complete `ReligiousBody` with membership data.

**Error Paths:**
- Transcriber can't see any records: They are not assigned any; contact PI
- Record is missing the original image: Note in transcription notes; PI follows up with Omeka
- Denomination not in dropdown: Transcriber adds note; PI adds new denomination to reference data

---

### Flow 2: Reviewing and Approving Transcriptions

**Goal:** Reviewer checks a completed transcription and approves or returns it

**Starting Point:** Reviewer logs into `/admin/`

**Steps:**
1. Dashboard shows the combined review queue count
2. Reviewer navigates to Census Schedules → filters by "Review Queue"
3. Opens a record → selects **Reconcile & approve**, then compares two distinct sources beside the original schedule image. Both selectors offer current canonical data, human snapshots, and agent outputs, so reviewers can compare snapshot-to-model, model-to-model, or canonical-to-evidence. The default pair is the newest human snapshot and newest agent output.
4. Selects baseline or comparison values by clicking their cells, optionally enters a typed reviewer correction through the selected cell's pencil action (or double-click), and explicitly retains/adds/removes unmatched related rows. AI-specific marginalia and agent notes come from the comparison evidence automatically and are not presented as source decisions.
5. Adds optional notes, checks the confirmation that the highlighted result should become canonical, and chooses **Apply and approve**. The server validates and applies the result atomically without a separate preview step.
6. The system infers whether the append-only provenance outcome retained canonical data, promoted one complete evidence source, or incorporated a mixed/edited result. Reviewer corrections are preserved as an `edited` source, and every selected transcription is linked to the event.
7. If neither is correct: Returns the record to `in_progress` and adds a note in `transcription_notes`
   - Transcriber will see the record reappear in their list with the reviewer's note

For trusted model runs, a Reviewer may instead select schedules in the admin list and choose **Promote latest model transcription**. After an explicit confirmation, each schedule independently promotes its newest agent run and becomes approved. **Restore previous canonical data** steps eligible schedules backward through unreversed reconciliation states while preserving every promotion and restore in the audit trail.

**Success Outcome:**
Record has `transcription_status = approved`; all data has been verified against the source image and the decision is preserved as append-only reconciliation evidence.

---

### Flow 3: Bulk Assigning Records

**Goal:** PI assigns a batch of unprocessed records to a student worker at the start of a work session

**Starting Point:** PI or Reviewer in Census Schedules admin list

**Steps:**
1. Filters list by `transcription_status = unassigned` and optionally by state/county/denomination
2. Selects 10–20 records using checkboxes
3. Chooses "Bulk Assign" from the actions dropdown → clicks "Go"
4. Bulk assign form appears with:
   - Dropdown: Select transcriber (shows Transcribers group members)
   - Dropdown: Select reviewer (shows Reviewers group members)
   - Checkbox: Change status to "Assigned"
5. PI submits → all selected records updated simultaneously
6. Confirmation message shows count of updated records

**Success Outcome:**
Selected records have `transcription_status = assigned` and show correct `assigned_transcriber`.

---

### Flow 4: Browsing Census Data (Public)

**Goal:** Historian finds congregation data for a specific city in 1926

**Starting Point:** User visits `https://religiousecologies.org/census/browser/`

**Steps:**
1. Browser page loads with state dropdown and empty results
2. User selects "New York" from state dropdown
3. County dropdown populates; user selects "Kings"
4. Populated place dropdown populates; user selects "Brooklyn"
5. Results list shows all congregations in Brooklyn with denomination and member counts
6. User clicks a congregation name → navigates to detail page
7. Detail page shows all transcribed fields: address, building value, finances, membership by age/sex, Sunday school, clergy

**Success Outcome:**
User finds and reads the complete data for a specific congregation in under 60 seconds.

**Error Paths:**
- Place selected but no records: "No records found for this location" message with suggestion to broaden search
- Record partially transcribed or awaiting review: It remains visible with its transcription status

---

## Out of Scope

### Not in Current Version (Future Enhancements)

- **Email notifications**: Automatic emails when a record is assigned or returned for correction — planned but not implemented
- **Deadline tracking**: Assignment due dates and overdue alerts for transcribers
- **Student dashboard**: A non-admin view showing a transcriber's personal progress and assigned work queue
- **Bulk export via UI**: Public bulk download of full dataset as CSV/JSON (currently admin-only via `export_by_location`)
- **Transcriber performance metrics**: Individual productivity reports (records per week, error rates)
- **Mobile transcription interface**: The admin is functional on mobile but not optimized for it
- **Automated geocoding**: Geocoding is a manual/command-driven process; automatic geocoding on save is not implemented

### Explicitly Excluded

- **Real-time collaboration**: Multiple users editing the same record simultaneously is not supported; Django admin is single-user per record
- **Public user accounts**: The public browser is read-only; public users cannot create accounts or save searches
- **IE11 support**: Not tested or supported
- **Offline mode**: No service worker or offline capability

### Out of Project Scope

- **Omeka integration maintenance**: The Omeka instance is maintained separately; this project only reads from its API
- **Image digitization**: Scanning and uploading census schedules to Omeka is handled outside this system
- **Denominational history editorial content**: Denomination taxonomy and family classifications are imported from external CSV; editorial decisions about classification belong to the research team's scholarly process

---

## Open Questions

### Data Questions

- **Q:** What is the intended handling of schedules that have no corresponding congregation data (e.g., blank or damaged images)?
  - **Context:** Some schedule images may be unusable. We need a status for "skip this record."
  - **Options:** Add a `skipped` status, use `transcription_notes` to mark as skip, add a boolean `is_unusable` field
  - **Owner:** PI + Eng
  - **Status:** Open

### Product Questions

- **Q:** Should the public census browser show the original schedule image?
  - **Context:** Images are stored locally after fetching from Omeka. Showing them to the public would be valuable for scholars, but increases storage/bandwidth and may have rights implications.
  - **Options:** Yes (link to image), Yes (embed thumbnail), No (staff only)
  - **Owner:** PI + Legal (rights)
  - **Status:** Open

- **Q:** What is the target completion date for a fully transcribed, approved dataset?
  - **Context:** Useful for planning student worker hours, scheduling publication
  - **Owner:** PI
  - **Status:** Open

### Technical Questions

- **Q:** Should geocoding be automated on save for new `ReligiousBody` records?
  - **Context:** Currently a manual/batch process. Auto-geocoding would improve data completeness but adds latency to saves and requires an external geocoding API.
  - **Options:** Auto-geocode on save (via Celery task), keep manual batch process, add a one-click geocode button in admin
  - **Owner:** Eng + PI
  - **Status:** Open

---

*Last Updated: 2026-02-19*
*This document is maintained for AI agent context and onboarding.*
