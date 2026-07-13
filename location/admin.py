from django.contrib import admin
from unfold.admin import ModelAdmin

from location.models import County, PopulatedPlace, State


@admin.register(State)
class StateAdmin(ModelAdmin):
    list_display = ["code", "name"]
    search_fields = ["code", "name"]
    ordering = ["name"]


@admin.register(County)
class CountyAdmin(ModelAdmin):
    list_display = ["name", "state", "ahcb_id"]
    list_filter = ["state"]
    search_fields = ["name", "ahcb_id", "state__name"]
    ordering = ["state", "name"]
    autocomplete_fields = ["state"]


@admin.register(PopulatedPlace)
class PopulatedPlaceAdmin(ModelAdmin):
    list_display = ["name", "county", "get_state", "lat", "lon"]
    list_filter = ["county__state"]
    search_fields = ["name", "place_id", "county__name", "county__state__name", "county__state__code"]
    ordering = ["county__state", "county", "name"]
    autocomplete_fields = ["county"]
    list_per_page = 50

    @admin.display(description="State")
    def get_state(self, obj):
        return obj.county.state.code

    def get_search_results(self, request, queryset, search_term):
        queryset, use_distinct = super().get_search_results(request, queryset, search_term)
        county_id = request.GET.get("county_id")
        if county_id:
            queryset = queryset.filter(county_id=county_id)
        return queryset, use_distinct
