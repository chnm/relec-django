from django.urls import path

from visualizations import views

urlpatterns = [
    # Legacy endpoint — primary routes are now under /visualizations/
    path("<slug:source>/geojson/", views.datalayer_geojson, name="datalayer_geojson_legacy"),
]
