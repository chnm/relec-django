from django.contrib import admin, messages
from import_export.admin import ImportExportModelAdmin
from unfold.admin import ModelAdmin
from unfold.contrib.import_export.forms import ExportForm, ImportForm

from .models import DataLayer
from .resources import DataLayerResource


def geocode_selected(modeladmin, request, queryset):
    """Geocode selected data layer records using Nominatim."""
    from census.geocoding import geocode_address, GeocodingError

    success = 0
    failed = 0
    skipped = 0

    for obj in queryset:
        # Build address from available fields
        address = obj.data.get("address", "") if isinstance(obj.data, dict) else ""
        if not address and not obj.city:
            skipped += 1
            continue

        try:
            lat, lon, status = geocode_address(
                address=address,
                city=obj.city or None,
                county=obj.county or None,
                state=obj.state or None,
            )
            if status == "success":
                obj.lat = lat
                obj.lon = lon
                obj.save(update_fields=["lat", "lon", "updated_at"])
                success += 1
            elif status == "skipped":
                skipped += 1
            else:
                failed += 1
        except GeocodingError:
            failed += 1

    messages.success(
        request,
        f"Geocoding complete: {success} succeeded, {failed} failed, {skipped} skipped.",
    )


geocode_selected.short_description = "Geocode selected records"


def match_locations(modeladmin, request, queryset):
    """Match text location fields to existing State/County/PopulatedPlace records."""
    from location.models import County, PopulatedPlace, State

    matched_county = 0
    matched_place = 0
    no_match = 0

    for obj in queryset:
        found_county = False
        found_place = False

        # Try to match county by name + state
        if obj.county and obj.state:
            state_obj = (
                State.objects.filter(name__iexact=obj.state).first()
                or State.objects.filter(code__iexact=obj.state).first()
            )
            if state_obj:
                county_obj = County.objects.filter(
                    name__iexact=obj.county, state=state_obj
                ).first()
                if county_obj:
                    obj.county_ref = county_obj
                    found_county = True
                    matched_county += 1

                    if obj.city:
                        place_obj = PopulatedPlace.objects.filter(
                            name__iexact=obj.city, county=county_obj
                        ).first()
                        if place_obj:
                            obj.populated_place_ref = place_obj
                            found_place = True
                            matched_place += 1

        if found_county or found_place:
            obj.save(update_fields=["county_ref", "populated_place_ref", "updated_at"])
        else:
            no_match += 1

    messages.success(
        request,
        f"Location matching complete: {matched_county} counties matched, "
        f"{matched_place} places matched, {no_match} unmatched.",
    )


match_locations.short_description = "Match locations to database"



@admin.register(DataLayer)
class DataLayerAdmin(ImportExportModelAdmin, ModelAdmin):
    import_form_class = ImportForm
    export_form_class = ExportForm
    resource_classes = [DataLayerResource]

    list_display = [
        "title",
        "source",
        "state",
        "county",
        "city",
        "has_schedule",
        "has_coordinates",
        "has_location_ref",
    ]
    list_filter = ["source", "state"]
    search_fields = ["title", "city", "county", "state"]
    autocomplete_fields = ["census_schedule", "county_ref", "populated_place_ref"]
    readonly_fields = ["created_at", "updated_at"]
    actions = [geocode_selected, match_locations]

    fieldsets = (
        (None, {
            "fields": ("title", "source"),
        }),
        ("Location (Text)", {
            "fields": ("city", "county", "state", "lat", "lon"),
        }),
        ("Location (Linked)", {
            "fields": ("county_ref", "populated_place_ref"),
            "description": "Matched references to existing location data. Use the 'Match locations' action to populate automatically.",
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

    @admin.display(boolean=True, description="Location")
    def has_location_ref(self, obj):
        return obj.county_ref_id is not None
