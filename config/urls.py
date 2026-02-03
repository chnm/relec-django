from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from debug_toolbar.toolbar import debug_toolbar_urls

from religious_ecologies.views import index

admin.site.site_header = "Religious Ecologies"
admin.site.site_title = "Religious Ecologies Data Admin"
admin.site.index_title = "Religious Ecologies Data Admin"

urlpatterns = [
    path("", index, name="index"),
    path("admin/", admin.site.urls),
    path("census/", include("census.urls")),
    path("analytics/", include("analytics.urls")),
    path("", include("pages.urls")),
    # allauth
    path("accounts/", include("allauth.urls")),
    # pages - keep this last so it doesn't interfere with other URL patterns
    path("", include("pages.urls")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

if settings.DEBUG:
    urlpatterns = [path("__debug__/", include(debug_toolbar_urls()))] + urlpatterns
    # Serve static files in development
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
