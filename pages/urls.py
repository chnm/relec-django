from django.urls import path

from . import views

app_name = "pages"

urlpatterns = [
    # Page detail view - this should come last to catch any slug
    path("<slug:slug>/", views.page_detail, name="page_detail"),
]
