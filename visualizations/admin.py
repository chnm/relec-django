from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import Visualization


@admin.register(Visualization)
class VisualizationAdmin(ModelAdmin):
    list_display = ["title", "slug", "render_type", "author", "published_date"]
    list_filter = ["render_type"]
    search_fields = ["title", "slug", "author"]
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = ["created_at", "updated_at"]

    fieldsets = (
        (None, {
            "fields": ("title", "slug", "abstract", "content"),
        }),
        ("Publication", {
            "fields": ("author", "published_date", "updated_date", "doi", "thumbnail_image", "thumbnail_description"),
        }),
        ("Rendering", {
            "fields": ("render_type", "custom_view_name", "datalayer_source", "script_file", "style_file"),
            "description": "Controls how this visualization is rendered. 'model' uses the content field, 'custom' routes to a named view, 'datalayer' renders a map from DataLayer points.",
        }),
        ("Metadata", {
            "fields": ("created_at", "updated_at"),
        }),
    )
