from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path

from religious_ecologies.views import index, robots_txt

from .sitemaps import (
    BlogPostSitemap,
    CensusBrowserStateSitemap,
    CensusDetailSitemap,
    PageSitemap,
    StaticViewSitemap,
    VisualizationSitemap,
)

sitemaps = {
    "static": StaticViewSitemap,
    "pages": PageSitemap,
    "blog": BlogPostSitemap,
    "visualizations": VisualizationSitemap,
    "census-states": CensusBrowserStateSitemap,
    "census-records": CensusDetailSitemap,
}

admin.site.site_header = "Religious Ecologies"
admin.site.site_title = "Religious Ecologies Data Admin"
admin.site.index_title = "Religious Ecologies Data Admin"

urlpatterns = [
    path("", index, name="index"),
    path("robots.txt", robots_txt, name="robots_txt"),
    path("admin/", admin.site.urls),
    path(
        "sitemap.xml",
        sitemap,
        {"sitemaps": sitemaps},
        name="django.contrib.sitemaps.views.sitemap",
    ),
    path("census/", include("census.urls")),
    path("visualizations/", include("visualizations.urls")),
    path("datalayers/", include("datalayers.urls")),
    path("analytics/", include("analytics.urls")),
    # pages - keep this last so it doesn't interfere with other URL patterns
    path("", include("pages.urls")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

if settings.DEBUG:
    # Serve static files in development
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
