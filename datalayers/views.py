import json

from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.template.loader import select_template
from django.views.decorators.cache import cache_page

from .models import DataLayer


@cache_page(60 * 15)
def datalayer_map_view(request, source):
    """
    Render a map visualization for a given data layer source.

    Template resolution order:
      1. templates/datalayers/<source>.html  (custom per-source template)
      2. templates/datalayers/map.html       (generic map fallback)
    """
    points = DataLayer.objects.filter(source=source, lat__isnull=False, lon__isnull=False)

    if not points.exists():
        raise Http404(f"No data layer found for source: {source}")

    # Build GeoJSON for the map
    features = []
    for point in points:
        properties = {
            "title": point.title,
            "city": point.city,
            "county": point.county,
            "state": point.state,
        }
        # Merge in the JSONB data
        if point.data:
            properties.update(point.data)
        # Add schedule link if available
        if point.census_schedule_id:
            properties["schedule_resource_id"] = point.census_schedule.resource_id

        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [point.lon, point.lat],
            },
            "properties": properties,
        })

    geojson = {
        "type": "FeatureCollection",
        "features": features,
    }

    # Get a display title from the source slug
    display_title = source.replace("-", " ").title()

    context = {
        "source": source,
        "display_title": display_title,
        "geojson_data": json.dumps(geojson),
        "point_count": len(features),
    }

    # Check for custom template, fall back to generic map
    template = select_template([
        f"datalayers/{source}.html",
        "datalayers/map.html",
    ])

    return render(request, template.template.name, context)


@cache_page(60 * 15)
def datalayer_geojson(request, source):
    """Return GeoJSON for a data layer source (API endpoint for JS consumption)."""
    points = DataLayer.objects.filter(source=source, lat__isnull=False, lon__isnull=False)

    features = []
    for point in points:
        properties = {
            "title": point.title,
            "city": point.city,
            "county": point.county,
            "state": point.state,
        }
        if point.data:
            properties.update(point.data)
        if point.census_schedule_id:
            properties["schedule_resource_id"] = point.census_schedule.resource_id

        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [point.lon, point.lat],
            },
            "properties": properties,
        })

    return JsonResponse({
        "type": "FeatureCollection",
        "features": features,
    })
