from django.urls import path

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
    path(
        "visualizations/<slug:slug>/",
        views.VisualizationDetailView.as_view(),
        name="visualization-detail",
    ),
    # Page detail view - this should come last to catch any slug
    path("<slug:slug>/", views.page_detail, name="page_detail"),
]
