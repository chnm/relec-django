from django.urls import path

from . import views

urlpatterns = [
    path("<slug:source>/", views.datalayer_map_view, name="datalayer_map"),
    path("<slug:source>/geojson/", views.datalayer_geojson, name="datalayer_geojson"),
]
