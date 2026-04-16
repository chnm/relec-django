from django.urls import path

from census import views as census_views

from . import views

urlpatterns = [
    # Blog URLs
    path("blog/", views.BlogListView.as_view(), name="blog-list"),
    path("blog/<slug:slug>/", views.BlogDetailView.as_view(), name="blog-detail"),
    # Visualization URLs
    path(
        "visualizations/",
        views.VisualizationListView.as_view(),
        name="visualization-list",
    ),
    # Custom visualization views (rendered by census app views)
    path(
        "visualizations/denomination-map/",
        census_views.map_view,
        name="denomination_map",
    ),
    path(
        "visualizations/demographics-map/",
        census_views.demographics_map_view,
        name="demographics_map",
    ),
    path(
        "visualizations/populated-places-map/",
        census_views.denomination_geojson_map_view,
        name="denomination_geojson_map",
    ),
    path(
        "visualizations/urban-congregations/",
        census_views.urban_congregations_map_view,
        name="urban_congregations_map",
    ),
    path(
        "visualizations/urban-congregations-simple/",
        census_views.urban_congregations_simple_view,
        name="urban_congregations_simple",
    ),
    # Generic visualization detail (for model-backed visualizations)
    path(
        "visualizations/<slug:slug>/",
        views.VisualizationDetailView.as_view(),
        name="visualization-detail",
    ),
    # Page detail view - this should come last to catch any slug
    path("<slug:slug>/", views.page_detail, name="page_detail"),
]
