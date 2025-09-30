from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views
from .api_views import DenominationViewSet, ReligiousBodyViewSet

router = DefaultRouter()
router.register(r"religious-bodies", ReligiousBodyViewSet)
router.register(r"denominations", DenominationViewSet)

urlpatterns = [
    # API endpoints
    path("api/", include(router.urls)),
    # Map views
    path("map/", views.map_view, name="denomination_map"),
    path("demographics-map/", views.demographics_map_view, name="demographics_map"),
    # Census browser views
    path("browser/", views.census_browser_view, name="census_browser"),
    path("record/<int:resource_id>/", views.census_detail_view, name="census_detail"),
    # Browse views
    path(
        "denominations/", views.denominations_browse_view, name="denominations_browse"
    ),
    path("locations/", views.locations_browse_view, name="locations_browse"),
]
