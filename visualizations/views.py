import json
import logging

import markdown
from django.conf import settings
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import select_template
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.views.generic import ListView

from census.models import Denomination
from datalayers.models import DataLayer

from .models import Visualization

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# List and Detail views
# ---------------------------------------------------------------------------


@method_decorator(cache_page(60 * 15), name="dispatch")
class VisualizationListView(ListView):
    model = Visualization
    template_name = "visualizations/visualization_list.html"
    context_object_name = "visualizations"
    paginate_by = 20

    def get_queryset(self):
        return Visualization.objects.all().order_by("-published_date")


@cache_page(60 * 15)
def visualization_detail(request, slug):
    """
    Unified visualization detail view. Dispatches to the correct
    rendering path based on the Visualization's render_type:

    - "model": Markdown content with optional JS (e.g., catholic-dioceses)
    - "custom": Census map view functions (e.g., denomination-map)
    - "datalayer": Data layer map from DataLayer points (e.g., dc-churches)
    """
    viz = get_object_or_404(Visualization, slug=slug)

    if viz.render_type == "custom":
        return _render_custom_view(request, viz)
    elif viz.render_type == "datalayer":
        return _render_datalayer(request, viz)
    else:
        return _render_model_detail(request, viz)


def _render_model_detail(request, viz):
    """Render a model-backed visualization with markdown content."""
    md = markdown.Markdown(extensions=["extra", "codehilite", "toc"])
    context = {
        "visualization": viz,
        "content_html": md.convert(viz.content),
    }

    # Load JSON data for specific visualizations
    if viz.slug == "catholic-dioceses":
        if hasattr(settings, "STATICFILES_DIRS") and settings.STATICFILES_DIRS:
            base_path = settings.STATICFILES_DIRS[0]
        else:
            base_path = settings.STATIC_ROOT

        dioceses_path = base_path / "data" / "catholic_dioceses.json"

        try:
            with open(dioceses_path, "r", encoding="utf-8") as f:
                context["dioceses_data"] = json.dumps(json.load(f))
            context["use_chnm_api_for_map"] = True
        except (FileNotFoundError, json.JSONDecodeError) as e:
            context["dioceses_data"] = "[]"
            context["use_chnm_api_for_map"] = False
            logger.warning(f"Error loading Catholic dioceses data: {e}")

    template = select_template([
        f"visualizations/{viz.slug}.html",
        "visualizations/visualization_detail.html",
    ])
    return render(request, template.template.name, context)


# Map from custom_view_name to the actual view function name in this module
_CUSTOM_VIEW_MAP = {
    "denomination_map": "map_view",
    "demographics_map": "demographics_map_view",
    "denomination_geojson_map": "denomination_geojson_map_view",
    "urban_congregations_map": "urban_congregations_map_view",
    "urban_congregations_simple": "urban_congregations_simple_view",
}


def _render_custom_view(request, viz):
    """Dispatch to a custom census map view function."""
    view_func_name = _CUSTOM_VIEW_MAP.get(viz.custom_view_name)
    if not view_func_name:
        raise Http404(f"No custom view configured for {viz.slug}")
    view_func = globals()[view_func_name]
    # Strip the @cache_page wrapper since the parent view already caches
    if hasattr(view_func, "__wrapped__"):
        return view_func.__wrapped__(request)
    return view_func(request)


# ---------------------------------------------------------------------------
# Census map views (moved from census/views.py)
# ---------------------------------------------------------------------------


@cache_page(60 * 15)
def map_view(request):
    """Render the denomination map view with denomination filters."""
    denominations = Denomination.objects.all().order_by("name")

    census_families = (
        Denomination.objects.values_list("family_census", flat=True)
        .distinct()
        .order_by("family_census")
    )
    relec_families = (
        Denomination.objects.values_list("family_relec", flat=True)
        .distinct()
        .order_by("family_relec")
    )

    context = {
        "denominations": denominations,
        "census_families": census_families,
        "relec_families": relec_families,
    }

    return render(request, "census/map.html", context)


@cache_page(60 * 15)
def demographics_map_view(request):
    """Render the demographics map view with demographic filters."""
    denominations = Denomination.objects.all().order_by("name")

    census_families = (
        Denomination.objects.values_list("family_census", flat=True)
        .distinct()
        .order_by("family_census")
    )
    relec_families = (
        Denomination.objects.values_list("family_relec", flat=True)
        .distinct()
        .order_by("family_relec")
    )

    context = {
        "denominations": denominations,
        "census_families": census_families,
        "relec_families": relec_families,
    }

    return render(request, "census/demographics_map.html", context)


def denomination_geojson_map_view(request):
    """Render the GeoJSON map for denominations by populated place."""
    return render(request, "census/denomination_geojson_map.html")


def urban_congregations_map_view(request):
    """Urban American Congregations Map visualization."""
    return render(request, "census/visualizations/urban_congregations_map.html")


def urban_congregations_simple_view(request):
    """Simplified Urban Congregations Map visualization."""
    return render(request, "census/visualizations/urban_congregations_simple.html")


# ---------------------------------------------------------------------------
# Data layer map views (moved from datalayers/views.py)
# ---------------------------------------------------------------------------


def _render_datalayer(request, viz):
    """Render a data layer map visualization."""
    source = viz.datalayer_source

    points = DataLayer.objects.filter(
        source=source, lat__isnull=False, lon__isnull=False
    ).select_related(
        "census_schedule__schedule_denomination",
    )

    if not points.exists():
        raise Http404(f"No data layer found for source: {source}")

    features = _build_datalayer_features(points)

    geojson = {
        "type": "FeatureCollection",
        "features": features,
    }

    content_html = ""
    if viz.content:
        md = markdown.Markdown(extensions=["extra", "codehilite", "toc"])
        content_html = md.convert(viz.content)

    context = {
        "source": source,
        "source_meta": viz,
        "display_title": viz.title,
        "content_html": content_html,
        "geojson_data": json.dumps(geojson),
        "point_count": len(features),
    }

    template = select_template([
        f"datalayers/{source}.html",
        "datalayers/map.html",
    ])

    return render(request, template.template.name, context)


def _build_datalayer_features(points):
    """Build GeoJSON features from DataLayer queryset."""
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
            schedule = point.census_schedule
            properties["schedule_resource_id"] = schedule.resource_id
            if schedule.schedule_denomination:
                properties["denomination"] = schedule.schedule_denomination.name
                properties["denomination_family"] = schedule.schedule_denomination.family_relec or ""

        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [point.lon, point.lat],
            },
            "properties": properties,
        })
    return features


@cache_page(60 * 15)
def datalayer_geojson_by_slug(request, slug):
    """Return GeoJSON for a data layer visualization (API endpoint)."""
    viz = get_object_or_404(Visualization, slug=slug, render_type="datalayer")

    points = DataLayer.objects.filter(
        source=viz.datalayer_source, lat__isnull=False, lon__isnull=False
    ).select_related(
        "census_schedule__schedule_denomination",
    )

    features = _build_datalayer_features(points)

    return JsonResponse({
        "type": "FeatureCollection",
        "features": features,
    })
