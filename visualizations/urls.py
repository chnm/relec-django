from django.urls import path

from . import views

urlpatterns = [
    path("", views.VisualizationListView.as_view(), name="visualization-list"),
    # Custom census map views
    path("denomination-map/", views.map_view, name="denomination_map"),
    path("demographics-map/", views.demographics_map_view, name="demographics_map"),
    path("populated-places-map/", views.denomination_geojson_map_view, name="denomination_geojson_map"),
    path("urban-congregations/", views.urban_congregations_map_view, name="urban_congregations_map"),
    path("urban-congregations-simple/", views.urban_congregations_simple_view, name="urban_congregations_simple"),
    # Data layer map views
    path("data/<slug:source>/", views.datalayer_map_view, name="datalayer_map"),
    path("data/<slug:source>/geojson/", views.datalayer_geojson, name="datalayer_geojson"),
    # Model-backed visualization detail (must be last — catches any slug)
    path("<slug:slug>/", views.VisualizationDetailView.as_view(), name="visualization-detail"),
]
