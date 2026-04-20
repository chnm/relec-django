# Data Layer Visualizations

This guide explains how to create map visualizations using the Data Layers system. Data layers store bespoke geographic data points that can optionally link to census schedule records.

## Overview

The data layers system has two parts:

1. **Data import** — upload CSV data through the Django admin
2. **Map visualization** — automatically generated, or custom per-dataset

Every imported dataset with a `source` identifier automatically gets a generic map at `/datalayers/<source>/`. For custom visualizations, create a source-specific template that overrides the default.

## Importing Data

### CSV Format

Prepare a CSV with these headers (all optional except `title`):

```
title,lat,lon,city,county,state,source,schedule_id
```

- **title** — Name of the data point (required)
- **lat/lon** — Coordinates (needed for map display)
- **city/county/state** — Location text fields for filtering
- **source** — Dataset identifier slug, e.g., `dc-churches` (groups the data)
- **schedule_id** — Links to a `CensusSchedule` by `resource_id` (optional; missing IDs are silently skipped)

**Any extra columns** are automatically stored in the JSONB `data` field. For example:

```csv
title,lat,lon,state,source,schedule_id,pastor_name,pastor_gender
First Spiritual Alliance,42.10245,-72.56882,Massachusetts,spiritualist-pastors,47261,Eli N. Barrett,Male
```

Here `pastor_name` and `pastor_gender` are not model fields — they'll be stored as `{"pastor_name": "Eli N. Barrett", "pastor_gender": "Male"}` in the `data` JSON field.

### Import Steps

1. Go to `/admin/datalayers/datalayer/`
2. Click **Import** (top right)
3. Choose your CSV file and format
4. Preview the import, then confirm

### Re-importing

The import uses `title` + `source` as the unique key. Re-importing the same CSV updates existing records rather than creating duplicates.

### Admin Actions

After import, select records and use these bulk actions:

- **Geocode selected records** — looks up lat/lon from address/location fields using Nominatim (1 request/sec rate limit)
- **Match locations to database** — links text county/state/city fields to existing `State`/`County`/`PopulatedPlace` records

## Automatic Map Visualization

Once data is imported with a `source` value and lat/lon coordinates, a map is automatically available at:

```
/datalayers/<source>/
```

For example: `/datalayers/dc-churches/`

The map appears on the `/visualizations/` page alongside other visualizations. It includes:
- Carto Positron base tiles (matching other project maps)
- Circle markers for each data point
- Click-to-select with a details panel showing all properties
- Links to census records when `schedule_id` was provided

A GeoJSON API endpoint is also available for JavaScript consumption:

```
/datalayers/<source>/geojson/
```

## Custom Visualizations

### Template Resolution

The view checks for templates in this order:

1. `templates/datalayers/<source>.html` — custom template for this source
2. `templates/datalayers/map.html` — generic fallback

To customize a visualization, create a source-specific template.

### Creating a Custom Template

Create `templates/datalayers/<source>.html` (e.g., `templates/datalayers/dc-churches.html`):

```html
{% extends "base.html" %}
{% load static %}

{% block title %}{{ display_title }} | American Religious Ecologies{% endblock %}

{% block extra_css %}
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
          integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY="
          crossorigin=""/>
    <style>
        #map { height: 650px; width: 100%; border-radius: 8px; }
        /* Add custom styles here */
    </style>
{% endblock %}

{% block content %}
<div class="max-w-7xl mx-auto">
    <h1 class="text-3xl font-bold text-gray-900 font-heading">{{ display_title }}</h1>
    <p class="text-gray-600 mt-2">{{ point_count }} locations mapped</p>

    <div id="map" class="mt-6"></div>

    <!-- Add custom UI elements: filters, charts, legends, etc. -->
</div>
{% endblock %}

{% block extra_js %}
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
            integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo="
            crossorigin=""></script>
    <script>
        // GeoJSON data is available as a JS variable
        const geojsonData = {{ geojson_data|safe }};

        // Build your custom visualization here
        const map = L.map('map');

        L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
            attribution: '&copy; OpenStreetMap contributors &copy; CARTO',
            subdomains: 'abcd',
            maxZoom: 20,
        }).addTo(map);

        const layer = L.geoJSON(geojsonData, {
            // Custom marker styling, popups, etc.
        }).addTo(map);

        map.fitBounds(layer.getBounds(), { padding: [30, 30] });
    </script>
{% endblock %}
```

### Available Context Variables

Every data layer view (generic or custom) receives these context variables:

| Variable | Type | Description |
|----------|------|-------------|
| `source` | string | The source slug (e.g., `dc-churches`) |
| `display_title` | string | Title-cased version of source (e.g., `Dc Churches`) |
| `geojson_data` | JSON string | GeoJSON FeatureCollection with all points |
| `point_count` | int | Number of mapped points |

### GeoJSON Feature Properties

Each feature's `properties` object contains:

- `title` — point title
- `city`, `county`, `state` — location text
- All keys from the JSONB `data` field (e.g., `address`, `zip_code`, `pastor_name`)
- `schedule_resource_id` — if linked to a census schedule

### Using the GeoJSON API

For more complex visualizations (Observable Plot, D3, etc.), you can fetch data from the API instead of using the embedded variable:

```javascript
fetch('/datalayers/dc-churches/geojson/')
    .then(r => r.json())
    .then(geojson => {
        // Build visualization with geojson.features
    });
```

## File Structure

```
datalayers/
├── models.py          — DataLayer model (title, lat/lon, location, schedule FK, JSONB data)
├── admin.py           — Admin with import/export, geocode, and match-locations actions
├── resources.py       — django-import-export resource with lenient FK and JSONB auto-collection
├── views.py           — Generic map view with template override support, GeoJSON API
├── urls.py            — /datalayers/<source>/ and /datalayers/<source>/geojson/
└── migrations/

templates/datalayers/
├── map.html           — Generic map template (Leaflet + Carto Positron)
└── <source>.html      — Custom per-source templates (optional)
```

## Checklist: Adding a New Data Layer Visualization

- [ ] Prepare CSV with `title`, `lat`, `lon`, `source`, and any extra columns
- [ ] Import via Django admin (`/admin/datalayers/datalayer/` → Import)
- [ ] Verify the generic map at `/datalayers/<source>/`
- [ ] (Optional) Run "Match locations" action to link to existing location data
- [ ] (Optional) Create `templates/datalayers/<source>.html` for custom visualization
- [ ] Check that it appears on the `/visualizations/` page
