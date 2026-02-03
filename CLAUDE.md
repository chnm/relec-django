# Religious Ecologies Project - Claude Code Session Notes

## Project Overview
Django project for managing historical religious census data transcription with undergraduate/graduate student workers.

## Recent Implementation: Complete Project Management System + Enhanced Admin

### ✅ Completed Work

#### 1. Lightweight Project Management System
**Files Modified:**
- `census/models.py` - Added transcription workflow fields to CensusSchedule model
- `census/admin.py` - Enhanced admin with project management features
- `census/management/commands/setup_transcription_groups.py` - User group setup command

**Features Implemented:**
- **Status Workflow**: `unassigned` → `assigned` → `in_progress` → `needs_review` → `completed` → `approved`
- **User Assignments**: `assigned_transcriber` and `assigned_reviewer` fields
- **Auto-status Logic**: Records auto-transition when assignments change
- **Permissions**: Students (Transcribers group) can add/edit but not delete; PIs (Reviewers group) have full access

#### 2. Django-Unfold Admin Enhancements
**Files Modified:**
- `config/settings.py` - Added comprehensive UNFOLD configuration with Religious Ecologies branding
- `templates/admin/index.html` - Custom dashboard with charts and metrics
- `religious_ecologies/admin.py` - Dashboard context injection
- `religious_ecologies/apps.py` - App config for admin loading
- `static/css/custom_unfold.css` - Custom Religious Ecologies blue theme (#0060b1)

**Features Implemented:**
- **Organized Sidebar**:
  - Dashboard
  - Data Quality Tools (Schedule ID gaps, Missing counties)
  - Transcription Project (census schedules, religious bodies, membership, clergy)
  - Reference Data (denominations, locations)
  - Content Management (pages)
  - System Administration (users, groups - tucked away)
- **Interactive Dashboard**:
  - Key metrics (total records, transcribed count, completion %)
  - Visual charts (status distribution, work distribution)
  - Recent activity feed with status badges
- **Religious Ecologies Branding**: Logo integration and custom blue color scheme

#### 3. Complete Bulk Assignment System
**Files Modified:**
- `census/admin.py` - Added comprehensive bulk actions and custom views
- `templates/admin/census/bulk_assign.html` - Professional bulk assignment interface
- `templates/admin/census/schedule_gap_analysis.html` - Schedule ID gap analysis
- `templates/admin/census/missing_county_analysis.html` - County data completeness analysis

**Features Implemented:**
- Status changes: Mark as unassigned/assigned/in progress/needs review/transcribed/approved
- Assignments: Assign to me, remove transcriber/reviewer assignments
- **Advanced bulk assign form**: Multi-user assignment with status changes
- **Data Quality Tools**: Gap analysis and location data validation

#### 4. Enhanced Admin Filtering & User Permissions
**Features Implemented:**
- **Smart Record Filtering**: Students see only assigned records, PIs see all records
- **Enhanced Filters**: Workflow filters, assignment status filters, location filters
- **User Permission Logic**: Intelligent access control based on group membership
- **Auto-save Logic**: Student work automatically transitions to "needs review" status

### 🔨 Commands for Setup
```bash
# Run migrations
poetry run python manage.py migrate

# Set up user groups and permissions
poetry run python manage.py setup_transcription_groups

# Check configuration
poetry run python manage.py check
```

### 📋 System Ready for Production Use

#### ✅ All Core Features Complete
- Bulk assignment system fully functional with professional interface
- User permissions system operational and tested
- Data quality analysis tools integrated
- Admin interface fully customized with Religious Ecologies branding

#### 🔧 Setup Required for New Deployments
- Add users to "Transcribers" and "Reviewers" groups via Django admin
- Configure user permissions for project team members
- Test workflow with actual transcription data

#### 💡 Future Enhancement Opportunities
- Email notifications for status changes
- Deadline tracking for assignments
- Progress reporting views for individual users
- Student dashboard showing personal assigned work
- Advanced batch assignment by location/denomination filters

### 🗂️ Key File Locations
```
├── census/
│   ├── models.py (CensusSchedule with workflow fields)
│   ├── admin.py (Complete admin with bulk actions, filters, custom views)
│   └── management/commands/setup_transcription_groups.py
├── config/settings.py (UNFOLD configuration with Religious Ecologies branding)
├── templates/admin/
│   ├── index.html (Custom dashboard)
│   └── census/
│       ├── bulk_assign.html (Bulk assignment interface)
│       ├── schedule_gap_analysis.html (Gap analysis tool)
│       └── missing_county_analysis.html (County analysis tool)
├── static/css/custom_unfold.css (Religious Ecologies blue theme)
├── religious_ecologies/
│   ├── admin.py (Dashboard context)
│   └── apps.py (App config)
└── DEVNOTES.md (Comprehensive user permission documentation)
```

### 🎯 Final Status Summary
- ✅ Complete project management workflow implemented and tested
- ✅ Professional admin interface with Religious Ecologies branding
- ✅ Interactive dashboard with metrics and charts
- ✅ Full bulk assignment system with professional interface
- ✅ Data quality analysis tools (Schedule gaps, County completeness)
- ✅ Smart user permission system (Students see assigned records, PIs see all)
- ✅ Enhanced filtering and workflow management
- ✅ Comprehensive documentation in DEVNOTES.md

### 🔧 Development Commands
```bash
# Poetry environment
poetry run python manage.py [command]

# Key commands used
poetry run python manage.py makemigrations census
poetry run python manage.py migrate
poetry run python manage.py setup_transcription_groups
poetry run python manage.py check
```

The project now has a professional transcription management interface with workflow tracking, team assignments, and administrative oversight capabilities. The main remaining work is finishing the bulk assignment template and setting up user groups for testing.

---

## Django 6.0 Async Compatibility Fix (Feb 2026)

### Issue
Django 6.0 runs in async mode by default (via ASGI), causing `SynchronousOnlyOperation` errors with django-debug-toolbar.

### Solution
**Disabled django-debug-toolbar** for Django 6.0 compatibility:
- Commented out in `config/settings.py`:
  - `INSTALLED_APPS += ["debug_toolbar"]`
  - `MIDDLEWARE += ["debug_toolbar.middleware.DebugToolbarMiddleware"]`
- Updated `config/urls.py` to conditionally include debug toolbar only if in INSTALLED_APPS

**Why:** Django Debug Toolbar makes synchronous database queries in its panels, which conflicts with Django 6.0's async context. The toolbar needs updates for full Django 6.0 compatibility.

**What Still Works:**
- ✅ Django Admin with Unfold styling
- ✅ Custom dashboard with metrics and charts
- ✅ All transcription management features
- ✅ Bulk assignment system

**To Re-enable Later:** Wait for django-debug-toolbar to release Django 6.0 compatible version, then uncomment the lines in settings.py.

---

## Interactive Visualizations with Observable Plot

### ✅ Completed Work (Feb 2026)

**Problem:** Blog posts migrated from Hugo had interactive visualizations using Observable Plot.js, but the ES6 module imports weren't working in Django without a bundler.

**Solution Implemented:**
- Added **import maps** to `templates/pages/blog_detail.html` to load Observable Plot and D3 from CDN
- Updated `static/viz/params.js` to dynamically get visualization div IDs from a global params object
- Modified `pages/management/commands/convert_hugo_shortcodes.py` to inject params setup script before viz loads
- Created `pages/management/commands/fix_interactive_viz.py` to update already-converted posts

**Files Modified:**
- `templates/pages/blog_detail.html` - Added import map for `@observablehq/plot` and `d3` from jsDelivr CDN, plus styling for `.viz-interactive` figures
- `static/viz/params.js` - Updated to read div ID from `window.__vizParams` global object set by inline script
- `pages/management/commands/convert_hugo_shortcodes.py` - Enhanced `convert_fig_interactive()` to inject params setup
- `pages/management/commands/fix_interactive_viz.py` - New command to update existing posts with new HTML structure

**How It Works:**
1. Hugo shortcode `{{< fig-interactive id="..." script="..." caption="..." title="..." >}}` converts to HTML `<figure>` with:
   - A `<div id="..." class="viz-container">` for the visualization
   - An inline wrapper `<script type="module">` that:
     - Creates a data URL blob exporting `{ id: 'div-id' }` as a module
     - Fetches the viz script, replaces `@params` import with the data URL
     - Creates another blob URL for the modified script and dynamically imports it
   - Import map in page header resolves `@observablehq/plot` and `d3` from CDN

2. Visualization scripts (e.g., `denominational-diversity.js`) import Plot.js and params:
   ```javascript
   import * as Plot from "@observablehq/plot";
   import * as params from "@params";  // Replaced at runtime with data URL
   // ... creates plot ...
   document.getElementById(params.id).appendChild(plot);
   ```

3. Each figure gets its own isolated params module via data URL
   - No global state means multiple visualizations work independently
   - The `@params` import is replaced at fetch-time with a unique blob URL per figure

**Posts with Interactive Visualizations:**
- `overview-of-cities-data` - 2 Plot.js visualizations (denominational diversity, membership proportion)
- `american-rescue-workers` - Interactive visualizations

**Commands:**
```bash
# Fix existing converted posts (already run)
uv run python manage.py fix_interactive_viz

# Convert new Hugo posts with shortcodes
uv run python manage.py convert_hugo_shortcodes
```

**Key Technical Details:**
- Uses ES6 import maps (no bundler needed) - modern browser feature
- Observable Plot loaded from `https://cdn.jsdelivr.net/npm/@observablehq/plot@0.6/+esm`
- D3 loaded from `https://cdn.jsdelivr.net/npm/d3@7/+esm`
- Each visualization uses a wrapper script with hardcoded div ID (no params system needed)
- CSS styling in blog_detail.html provides consistent figure appearance

**Current Implementation (Simplified):**
After several iterations, we settled on the simplest approach:
- Each visualization has a wrapper script (e.g., `denominational-diversity-wrapper.js`)
- The wrapper has the target div ID hardcoded as a constant
- No global state, no params resolution, no data URLs
- Just straightforward ES6 modules that import Plot, import data, create viz, append to div

**Adding New Interactive Visualizations:**
See detailed guide in `docs/INTERACTIVE_VISUALIZATIONS.md` for complete instructions on:
- Creating data files
- Writing wrapper scripts
- Adding HTML to blog posts
- Troubleshooting common issues
