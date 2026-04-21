from django.urls import path

from visualizations import views

urlpatterns = [
    # Legacy endpoint — primary routes are now under /visualizations/<slug>/geojson/
    path("<slug:source>/geojson/", views.datalayer_geojson_by_slug, name="datalayer_geojson_legacy"),
]
