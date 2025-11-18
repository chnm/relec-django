import datetime
import os

import requests
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from requests.adapters import HTTPAdapter
from requests.exceptions import RequestException
from unfold.admin import ModelAdmin, StackedInline
from urllib3.util.retry import Retry

from .models import CensusSchedule, Clergy, Denomination, Membership, ReligiousBody


def get_requests_session(retries=3, backoff_factor=0.3):
    """Configure a requests session with retries and backoff"""
    session = requests.Session()
    retry_strategy = Retry(
        total=retries,
        backoff_factor=backoff_factor,
        status_forcelist=[429, 500, 502, 503, 504],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


# The following applies Unfold to the User model
admin.site.unregister(User)


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    pass


class ClergyInline(StackedInline):
    model = Clergy
    extra = 1
    tab = True


class MembershipInline(StackedInline):
    model = Membership
    extra = 1
    tab = True


class ReligiousBodyInline(StackedInline):
    model = ReligiousBody
    raw_id_fields = [
        "location",
    ]
    extra = 1
    tab = True


@admin.action(description="Fetch denominations from Apiary")
def sync_denominations(modeladmin, request, queryset):
    """Custom admin action to sync denominations from the API."""
    # Setup error logging
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)
    error_log = open(f"{log_dir}/sync_denominations_errors_{timestamp}.log", "w")

    skipped_count = 0
    success_count = 0

    try:
        # Fetch data from API
        session = get_requests_session()
        response = session.get(
            "https://data.chnm.org/relcensus/denominations", timeout=120
        )
        response.raise_for_status()
        denominations_data = response.json()

        for denom_data in denominations_data:
            # Check if any string field exceeds maximum length
            too_long = False
            for field, value in denom_data.items():
                if isinstance(value, str):
                    max_length = 50 if field == "denomination_id" else 255
                    if len(value) > max_length:
                        error_message = f"Skipping denomination with id={denom_data.get('denomination_id', 'unknown')}: {field} value exceeds {max_length} characters ({len(value)} chars)"
                        error_log.write(f"{datetime.datetime.now()}: {error_message}\n")
                        too_long = True
                        break

            if too_long:
                skipped_count += 1
                continue

            try:
                # Map the API response fields to our model fields
                Denomination.objects.update_or_create(
                    denomination_id=denom_data["denomination_id"],
                    defaults={
                        "name": denom_data["name"],
                        "short_name": denom_data["short_name"],
                        "family_relec": denom_data.get("family_relec", ""),
                        "family_census": denom_data.get("family_census", ""),
                    },
                )
                success_count += 1
            except Exception as e:
                error_message = f"Error saving denomination with id={denom_data.get('denomination_id', 'unknown')}: {str(e)}"
                error_log.write(f"{datetime.datetime.now()}: {error_message}\n")
                skipped_count += 1

        modeladmin.message_user(
            request,
            f"Synchronized {success_count} denominations, skipped {skipped_count} denominations with values exceeding maximum length",
            level=messages.SUCCESS,
        )
    except RequestException as e:
        modeladmin.message_user(
            request,
            f"Connection error: {str(e)}. Make sure the API is accessible at https://data.chnm.org/relcensus/denominations",
            level=messages.ERROR,
        )
    finally:
        error_log.close()


@admin.register(Denomination)
class DenominationAdmin(ModelAdmin):
    list_display = ["name", "denomination_id", "family_census", "family_relec"]
    search_fields = ["name", "denomination_id"]
    ordering = ["name"]
    list_filter = ["family_census", "family_relec"]
    actions = [sync_denominations]

    # Add history view
    history_list_display = ["changed_fields"]


@admin.register(CensusSchedule)
class CensusScheduleAdmin(ModelAdmin):
    list_display = [
        "schedule_title",
        "schedule_id",
        "resource_id",
    ]
    search_fields = ["schedule_title", "schedule_id", "resource_id"]

    readonly_fields = [
        "datascribe_omeka_item_id",
        "datascribe_item_id",
        "datascribe_record_id",
        "datascribe_original_image_path",
        "omeka_storage_id",
    ]

    fieldsets = [
        (
            "Schedule Information",
            {
                "fields": [
                    "resource_id",
                    "schedule_title",
                    "schedule_id",
                    "box",
                    "notes",
                ]
            },
        ),
        (
            "DataScribe Reference",
            {
                "fields": [
                    "datascribe_omeka_item_id",
                    "datascribe_item_id",
                    "datascribe_record_id",
                    "datascribe_original_image_path",
                    "omeka_storage_id",
                ],
            },
        ),
    ]
    inlines = [ReligiousBodyInline, MembershipInline, ClergyInline]

    history_list_display = ["changed_fields"]


@admin.register(Clergy)
class ClergyAdmin(ModelAdmin):
    list_display = [
        "name",
        "is_assistant",
        "serving_congregation_display",
        "college",
        "theological_seminary",
        "num_other_churches_served",
    ]
    list_filter = ["is_assistant"]
    search_fields = ["name", "college", "theological_seminary"]

    fieldsets = [
        (
            "Basic Information",
            {"fields": ["name", "is_assistant", "serving_congregation"]},
        ),
        ("Education", {"fields": ["college", "theological_seminary"]}),
        ("Service Details", {"fields": ["num_other_churches_served"]}),
    ]

    def serving_congregation_display(self, obj):
        return obj.serving_congregation

    serving_congregation_display.short_description = "Serving Congregation"
    serving_congregation_display.boolean = True

    history_list_display = ["changed_fields"]


@admin.register(ReligiousBody)
class ReligiousBodyAdmin(ModelAdmin):
    """
    Admin interface for Religious Body records with geocoding support.
    """

    list_display = [
        "name",
        "denomination",
        "address",
        "location",
        "latitude",
        "longitude",
    ]

    list_filter = [
        "geocode_status",
        ("location__state", admin.EmptyFieldListFilter),
    ]

    search_fields = [
        "name",
        "address",
        "denomination__name",
        "location__city",
        "location__county",
        "location__state",
    ]

    raw_id_fields = ["location", "census_record", "denomination"]

    readonly_fields = [
        "geocode_status",
        "geocoded_at",
        "created_at",
        "updated_at",
    ]

    fieldsets = [
        (
            "Basic Information",
            {
                "fields": [
                    "census_record",
                    "name",
                    "denomination",
                    "census_code",
                    "division",
                ]
            },
        ),
        (
            "Location & Address",
            {
                "fields": [
                    "address",
                    "location",
                    "urban_rural_code",
                ]
            },
        ),
        (
            "Geocoding (Auto-populated)",
            {
                "fields": [
                    "latitude",
                    "longitude",
                    "geocode_status",
                    "geocoded_at",
                ],
                "classes": ["collapse"],
            },
        ),
        (
            "Church Property",
            {
                "fields": [
                    "num_edifices",
                    "edifice_value",
                    "edifice_debt",
                ],
                "classes": ["collapse"],
            },
        ),
        (
            "Parsonage",
            {
                "fields": [
                    "has_pastors_residence",
                    "residence_value",
                    "residence_debt",
                ],
                "classes": ["collapse"],
            },
        ),
        (
            "Finances",
            {
                "fields": [
                    "expenses",
                    "benevolences",
                    "total_expenditures",
                ],
                "classes": ["collapse"],
            },
        ),
        (
            "Record Information",
            {
                "fields": [
                    "created_at",
                    "updated_at",
                ],
                "classes": ["collapse"],
            },
        ),
    ]

    def geocode_status_display(self, obj):
        """Display geocoding status with color coding."""
        if obj.geocode_status == "success":
            return "✓ Geocoded"
        elif obj.geocode_status == "failed":
            return "✗ Failed"
        elif obj.geocode_status == "pending":
            return "⏳ Pending"
        elif obj.geocode_status == "skipped":
            return "− Skipped"
        return "− Not Attempted"

    geocode_status_display.short_description = "Geocode Status"

    history_list_display = ["changed_fields"]
