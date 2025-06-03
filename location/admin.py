import datetime
import os

import requests
from django.contrib import admin, messages
from requests.exceptions import RequestException
from unfold.admin import ModelAdmin

from location.models import Location


@admin.action(description="Sync locations from API")
def sync_locations(modeladmin, request, queryset):
    """Custom admin action to sync locations from the API."""
    # Setup error logging
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)
    error_log = open(f"{log_dir}/sync_locations_errors_{timestamp}.log", "w")

    skipped_count = 0
    success_count = 0

    try:
        # Fetch data from API
        response = requests.get("https://data.chnm.org/relcensus/cities", timeout=30)
        response.raise_for_status()
        locations_data = response.json()

        for loc_data in locations_data:
            # Check if any string field exceeds 250 characters
            too_long = False
            for field, value in loc_data.items():
                if isinstance(value, str) and len(value) > 250:
                    error_message = f"Skipping location with place_id={loc_data.get('place_id', 'unknown')}: {field} value exceeds 250 characters ({len(value)} chars)"
                    error_log.write(f"{datetime.datetime.now()}: {error_message}\n")
                    too_long = True
                    break

            if too_long:
                skipped_count += 1
                continue

            try:
                # Map the API response fields to our model fields
                Location.objects.update_or_create(
                    place_id=loc_data["place_id"],
                    city=loc_data["city"],
                    county=loc_data["county"],
                    state=loc_data["state"],
                    map_name=loc_data["map_name"],
                    county_ahcb=loc_data["county_ahcb"],
                    defaults={
                        "lon": loc_data["lon"],
                        "lat": loc_data["lat"],
                    },
                )
                success_count += 1
            except Exception as e:
                error_message = f"Error saving location with place_id={loc_data.get('place_id', 'unknown')}: {str(e)}"
                error_log.write(f"{datetime.datetime.now()}: {error_message}\n")
                skipped_count += 1

        modeladmin.message_user(
            request,
            f"Synchronized {success_count} locations, skipped {skipped_count} locations with values exceeding 250 characters",
            level=messages.SUCCESS,
        )
    except RequestException as e:
        modeladmin.message_user(
            request,
            f"Connection error: {str(e)}. Make sure the API server is running at https://data.chnm.org",
            level=messages.ERROR,
        )
    finally:
        error_log.close()


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
    actions = [sync_locations]

    fieldsets = [
        (
            "Location Information",
            {"fields": ("map_name", "place_id", "city", "county", "state")},
        ),
        ("Geographic Coordinates", {"fields": ("lat", "lon")}),
        ("County AHCB", {"fields": ("county_ahcb",)}),
    ]
