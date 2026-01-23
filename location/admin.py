from django.contrib import admin
from unfold.admin import ModelAdmin

from location.models import Location


@admin.register(Location)
class LocationAdmin(ModelAdmin):
    search_fields = [
        "map_name",
        "city",
        "county",
        "state",
    ]

    list_display = [
        "map_name",
        "city",
        "county",
        "state",
        "lat",
        "lon",
    ]

    list_filter = [
        "state",
    ]
    list_per_page = 50

    fieldsets = [
        (
            "Location Information",
            {"fields": ("map_name", "place_id", "city", "county", "state")},
        ),
        ("Geographic Coordinates", {"fields": ("lat", "lon")}),
        ("County AHCB", {"fields": ("county_ahcb",)}),
    ]
