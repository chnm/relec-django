from django.urls import path

from . import views

urlpatterns = [
    path("", views.VisualizationListView.as_view(), name="visualization-list"),
    # GeoJSON API for data layer maps
    path("<slug:slug>/geojson/", views.datalayer_geojson_by_slug, name="datalayer_geojson"),
    # Unified detail view — dispatches by render_type
    path("<slug:slug>/", views.visualization_detail, name="visualization-detail"),
]
