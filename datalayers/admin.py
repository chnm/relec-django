from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import DataLayer


@admin.register(DataLayer)
class DataLayerAdmin(ModelAdmin):
    list_display = ["title", "source", "state", "county", "city", "has_schedule", "has_coordinates"]
    list_filter = ["source", "state"]
    search_fields = ["title", "city", "county", "state"]
    autocomplete_fields = ["census_schedule"]
    readonly_fields = ["created_at", "updated_at"]

    fieldsets = (
        (None, {
            "fields": ("title", "source"),
        }),
        ("Location", {
            "fields": ("city", "county", "state", "lat", "lon"),
        }),
        ("Census Link", {
            "fields": ("census_schedule",),
        }),
        ("Custom Data", {
            "fields": ("data",),
        }),
        ("Metadata", {
            "fields": ("created_at", "updated_at"),
        }),
    )

    @admin.display(boolean=True, description="Schedule")
    def has_schedule(self, obj):
        return obj.census_schedule_id is not None

    @admin.display(boolean=True, description="Coords")
    def has_coordinates(self, obj):
        return obj.lat is not None and obj.lon is not None
