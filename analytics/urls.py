from django.urls import path

from . import views

app_name = "analytics"

urlpatterns = [
    path("", views.analytics_home, name="home"),
    path("query/", views.query_builder, name="query_builder"),
    path("query/results/", views.run_query, name="run_query"),
    path(
        "analysis/denominations/",
        views.denomination_analysis,
        name="denomination_analysis",
    ),
    path("analysis/locations/", views.location_analysis, name="location_analysis"),
    path("analysis/completeness/", views.data_completeness, name="data_completeness"),
    path(
        "analysis/transcription-progress/",
        views.transcription_progress,
        name="transcription_progress",
    ),
    path(
        "analysis/missing-place-ids/", views.missing_place_ids, name="missing_place_ids"
    ),
]
