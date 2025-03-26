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
    # Map view
    path("map/", views.map_view, name="denomination_map"),
]
