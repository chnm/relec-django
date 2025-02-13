from django.contrib import admin
from unfold.admin import ModelAdmin, StackedInline, TabularInline

from location.models import City, County, Location, State, UnlistedLocation


@admin.register(Location)
class LocationAdmin(ModelAdmin):
    search_fields = [
        "map_name",
        "city__name",
        "county__name",
        "state__name",
        "state__abbreviation",
    ]

    list_display = [
        "map_name",
        "get_city",
        "get_county",
        "get_state",
        "lat",
        "lon",
    ]

    list_filter = [
        "state__name",
    ]
    list_per_page = 50

    def get_city(self, obj):
        return obj.city.name

    get_city.short_description = "City"
    get_city.admin_order_field = "city__name"

    def get_county(self, obj):
        return obj.county.name

    get_county.short_description = "County"
    get_county.admin_order_field = "county__name"

    def get_state(self, obj):
        return obj.state.abbreviation

    get_state.short_description = "State"
    get_state.admin_order_field = "state__abbreviation"

    # Optional: Add fieldsets for better organization in the edit form
    fieldsets = [
        (
            "Location Information",
            {"fields": ("map_name", "place_id", "city", "county", "state")},
        ),
        ("Geographic Coordinates", {"fields": ("lat", "lon")}),
        ("County AHCB", {"fields": ("county_ahcb",)}),
    ]


@admin.register(State)
class StateAdmin(ModelAdmin):
    list_display = ["name", "abbreviation"]
    search_fields = ["name", "abbreviation"]
    ordering = ["name"]


@admin.register(County)
class CountyAdmin(ModelAdmin):
    list_display = ["name", "state"]
    list_filter = ["state"]
    search_fields = ["name", "state__name"]
    ordering = ["state", "name"]


@admin.register(City)
class CityAdmin(ModelAdmin):
    list_display = ["name", "county", "state"]
    list_filter = ["state"]
    search_fields = ["name", "county__name", "state__name"]
    ordering = ["state", "name"]


@admin.register(UnlistedLocation)
class UnlistedLocationAdmin(ModelAdmin):
    list_display = ["name", "county", "state"]
    list_filter = ["state"]
    search_fields = ["name", "county__name", "state__name", "notes"]
    ordering = ["state", "name"]
