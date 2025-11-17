# Analytics App

Internal data exploration and analysis tools for staff and reviewers.

## Overview

The analytics app provides advanced querying, data visualization, and export capabilities for internal users. It's designed to complement (not replace) the Django admin interface, keeping admin focused on CRUD operations while providing powerful analytical tools here.

## Features

### 1. Query Builder (`/analytics/query/`)
Build advanced queries with multiple filters:

#### Denomination Filtering (Tabbed Interface)
Three ways to filter by denomination:
- **Census Families**: Original census family groupings (e.g., "Baptist bodies", "Adventist bodies")
- **Religious Ecologies Families**: Research-based family groupings (e.g., "Baptist", "Catholic", "Adventist")
- **Individual Denominations**: Specific denominations (e.g., "Southern Baptist Convention"), organized by family

Users can select multiple items within any tab. Selections across different tabs are combined with OR logic.

#### Other Filters
- **Location filters**: State, county, city
- **Transcription status**: Filter by workflow status
- **Data completeness**: Find records with/without membership or clergy data
- **Property values**: Filter by edifice value ranges
- **Export options**: View results on-page (limited to 100), or export to CSV/JSON (all results)

### 2. Denomination Analysis (`/analytics/analysis/denominations/`)
Aggregate statistics by denomination:
- Total religious bodies per denomination
- Total edifices
- Total edifice value
- Direct links to query all records for a denomination

### 3. Location Analysis (`/analytics/analysis/locations/`)
Geographic analysis:
- **State-level**: View counts by state with links to drill down
- **County-level**: Click a state to see county breakdown
- Links to query all records for a location

### 4. Data Completeness Report (`/analytics/analysis/completeness/`)
Track transcription progress:
- Percentage of schedules with religious bodies
- Percentage with membership data
- Percentage with clergy data
- Location data completeness (has location, has county)
- Quick links to find incomplete records

## Access Control

All analytics views require users to be:
- Staff members (`is_staff=True`), OR
- Members of the "Reviewers" group

Regular transcribers do NOT have access to analytics (they see filtered data in admin).

## Query Logic

### Denomination Filtering
- **Census Family OR RelEc Family OR Individual Denominations**: Selections across different denomination filter types use OR logic
- **Multiple selections within a filter**: Use OR logic (e.g., selecting "Baptist" and "Methodist" families returns records from either family)
- **Denomination + Other Filters**: Denomination filters are combined with other filters (location, status, etc.) using AND logic

### Example Queries
- **All Baptist bodies in Virginia**: Select "Baptist" from RelEc Families tab + "VA" from state dropdown
- **Specific denominations in multiple states**: Select individual denominations + multiple states
- **Census family comparison**: Select "Baptist bodies" from Census Families to see the historical grouping

## Exports

### CSV Export
- Contains all matching results (not limited to 100)
- Includes admin URL for each record for easy editing
- Columns: Schedule ID, Religious Body Name, Denomination, State, County, City, Address, Num Edifices, Edifice Value, Transcription Status, Admin Link

### JSON Export
- Structured JSON format
- Contains same data as CSV
- Suitable for programmatic access or integration with other tools

## URL Structure

```
/analytics/                              # Analytics home
/analytics/query/                        # Query builder form
/analytics/query/results/                # Query results (GET params)
/analytics/analysis/denominations/       # Denomination analysis
/analytics/analysis/locations/           # Location analysis (state)
/analytics/analysis/locations/?state=XX  # Location analysis (county)
/analytics/analysis/completeness/        # Data completeness report
```

## Integration with Admin

The analytics app is integrated into the Django admin sidebar under "Analytics & Reporting". All pages maintain the Religious Ecologies branding and Tailwind design system.

## Performance

All views use optimized queries with:
- `select_related()` for foreign key relationships
- `prefetch_related()` for reverse relationships
- Query result limits for HTML views (100 records max)
- Database indexes on commonly filtered fields

## Future Enhancements

Potential additions:
- Data visualizations (charts, graphs)
- Saved queries
- Scheduled exports
- Email reports
- Timeline analysis
- Batch data operations

## Development Notes

- Views: `analytics/views.py`
- URLs: `analytics/urls.py`
- Templates: `templates/analytics/`
- Permission check: `is_staff_or_reviewer()` decorator on all views
