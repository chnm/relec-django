import debug_toolbar
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from religious_ecologies.views import index

admin.site.site_header = "Religious Ecologies"
admin.site.site_title = "Religious Ecologies Data Admin"
admin.site.index_title = "Religious Ecologies Data Admin"

urlpatterns = [
    path("", index, name="index"),
    path("admin/", admin.site.urls),
    path("census/", include("census.urls")),
    # allauth
    path("accounts/", include("allauth.urls")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

if settings.DEBUG:
    urlpatterns = [path("__debug__/", include(debug_toolbar.urls))] + urlpatterns
