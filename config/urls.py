from django.contrib import admin
from django.urls import path
from django.conf.urls import include

admin.site.site_header = "RelEc Data Administration"
admin.site.site_title = "Religious Ecologies"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("allauth.urls")),
]
