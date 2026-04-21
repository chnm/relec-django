import json
import logging

import markdown
from django.conf import settings
from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.template.loader import select_template
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.views.generic import DetailView, ListView

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


@method_decorator(cache_page(60 * 15), name="dispatch")
class VisualizationDetailView(DetailView):
    """Renders model-backed visualizations (render_type='model')."""

    model = Visualization
    template_name = "visualizations/visualization_detail.html"
    context_object_name = "visualization"
    slug_field = "slug"

    def get_queryset(self):
        return Visualization.objects.filter(render_type="model")

    def get_template_names(self):
        custom_template = f"visualizations/{self.object.slug}.html"
        return [custom_template, self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        md = markdown.Markdown(
            extensions=["extra", "codehilite", "toc"]
        )
        context["content_html"] = md.convert(self.object.content)

        # Load JSON data for specific visualizations
        if self.object.slug == "catholic-dioceses":
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

        return context


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


@cache_page(60 * 15)
def datalayer_map_view(request, source):
    """
    Render a map visualization for a given data layer source.

    Template resolution order:
      1. templates/datalayers/<source>.html  (custom per-source template)
      2. templates/datalayers/map.html       (generic map fallback)
    """
    points = DataLayer.objects.filter(
        source=source, lat__isnull=False, lon__isnull=False
    ).select_related(
        "census_schedule__schedule_denomination",
    )

    if not points.exists():
        raise Http404(f"No data layer found for source: {source}")

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

    geojson = {
        "type": "FeatureCollection",
        "features": features,
    }

    # Look up visualization metadata
    viz = Visualization.objects.filter(slug=source, render_type="datalayer").first()
    display_title = viz.title if viz else source.replace("-", " ").title()

    content_html = ""
    if viz and viz.content:
        md = markdown.Markdown(extensions=["extra", "codehilite", "toc"])
        content_html = md.convert(viz.content)

    context = {
        "source": source,
        "source_meta": viz,
        "display_title": display_title,
        "content_html": content_html,
        "geojson_data": json.dumps(geojson),
        "point_count": len(features),
    }

    template = select_template([
        f"datalayers/{source}.html",
        "datalayers/map.html",
    ])

    return render(request, template.template.name, context)


@cache_page(60 * 15)
def datalayer_geojson(request, source):
    """Return GeoJSON for a data layer source (API endpoint)."""
    points = DataLayer.objects.filter(
        source=source, lat__isnull=False, lon__isnull=False
    ).select_related(
        "census_schedule__schedule_denomination",
    )

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

    return JsonResponse({
        "type": "FeatureCollection",
        "features": features,
    })
