from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views
from .api_root import api_root
from .api_views import DenominationViewSet, ReligiousBodyViewSet

router = DefaultRouter()
router.register(r"religious-bodies", ReligiousBodyViewSet)
router.register(r"denominations", DenominationViewSet)

urlpatterns = [
    # API Documentation
    path("api/docs/", views.api_documentation_view, name="api_documentation"),
    # Custom API root
    path("api/", api_root, name="census-api-root"),
    # API endpoints
    path("api/", include(router.urls)),
    # Census browser views
    path("browser/", views.census_browser_view, name="census_browser"),
    path(
        "browser/<str:state_code>/",
        views.census_browser_view,
        name="census_browser_state",
    ),
    path(
        "browser/<str:state_code>/<str:county_name>/",
        views.census_browser_view,
        name="census_browser_county",
    ),
    path("record/<int:resource_id>/", views.census_detail_view, name="census_detail"),
    # Browse views
    path(
        "denominations/", views.denominations_browse_view, name="denominations_browse"
    ),
    path("locations/", views.locations_browse_view, name="locations_browse"),
    path(
        "populated-places/",
        views.populated_places_browse_view,
        name="browse_popplaces",
    ),
]
