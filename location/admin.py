from django.contrib import admin

from unfold.admin import ModelAdmin, StackedInline, TabularInline

from location.models import Location, City, County, State


@admin.register(Location)
class LocationAdmin(ModelAdmin):
    list_display = ["place_id", "map_name", "state", "city", "lat", "lon"]


@admin.register(City)
class CityAdmin(ModelAdmin):
    list_display = ["name", "state", "county"]


@admin.register(County)
class CountyAdmin(ModelAdmin):
    list_display = ["name", "state"]


@admin.register(State)
class StateAdmin(ModelAdmin):
    list_display = ["name", "abbreviation"]
