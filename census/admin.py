from django.contrib import admin
from django.utils.html import format_html
from unfold.admin import ModelAdmin, StackedInline

from .models import CensusSchedule, Clergy, Denomination, Membership, ReligiousBody


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


@admin.register(Denomination)
class DenominationAdmin(ModelAdmin):
    list_display = ["name", "denomination_id", "family_census", "family_arda"]
    search_fields = ["name", "denomination_id"]
    ordering = ["name"]
    list_filter = ["family_census", "family_arda"]

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


@admin.register(ReligiousBody)
class ReligiousBodyAdmin(ModelAdmin):
    list_display = [
        "name",
        "census_code",
        "denomination",
        "location",
    ]
    list_filter = [
        "denomination",
        "division",
        "urban_rural_code",
        "has_pastors_residence",
    ]
    search_fields = ["name", "census_code", "address"]
    autocomplete_fields = ["location"]

    fieldsets = [
        (
            "Religious Body Information",
            {
                "fields": [
                    "denomination",
                    "census_record",
                    "name",
                    "census_code",
                    "division",
                ]
            },
        ),
        ("Location", {"fields": ["location", "address", "urban_rural_code"]}),
        (
            "Property Details",
            {"fields": ["num_edifices", "edifice_value", "edifice_debt"]},
        ),
        (
            "Parsonage",
            {"fields": ["has_pastors_residence", "residence_value", "residence_debt"]},
        ),
        ("Finances", {"fields": ["expenses", "benevolences", "total_expenditures"]}),
    ]

    def total_value(self, obj):
        edifice = obj.edifice_value or 0
        residence = obj.residence_value or 0
        total = edifice + residence
        return format_html("${:,.2f}", total)

    total_value.short_description = "Total Property Value"

    history_list_display = ["changed_fields"]


@admin.register(Membership)
class MembershipAdmin(ModelAdmin):
    list_display = [
        "religious_body",
        "total_members",
        "male_members",
        "female_members",
        "members_under_13",
        "members_13_and_older",
    ]
    fieldsets = [
        (
            "Sunday School",
            {
                "fields": [
                    "sunday_school_num_officers_teachers",
                    "sunday_school_num_scholars",
                ]
            },
        ),
        (
            "Vacation Bible School",
            {"fields": ["vbs_num_officers_teachers", "vbs_num_scholars"]},
        ),
        (
            "Parochial School",
            {
                "fields": [
                    "parochial_num_administrators",
                    "parochial_num_elementary_teachers",
                    "parochial_num_secondary_teachers",
                    "parochial_num_elementary_scholars",
                    "parochial_num_secondary_scholars",
                ]
            },
        ),
    ]

    readonly_fields = ["total_members"]

    def total_members(self, obj):
        return obj.male_members + obj.female_members

    total_members.short_description = "Total Members"

    history_list_display = ["changed_fields"]


@admin.register(Clergy)
class ClergyAdmin(ModelAdmin):
    list_display = [
        "name",
        "is_assistant",
        "college",
        "theological_seminary",
        "num_other_churches_served",
    ]
    list_filter = ["is_assistant"]
    search_fields = ["name", "college", "theological_seminary"]

    fieldsets = [
        ("Basic Information", {"fields": ["name", "is_assistant"]}),
        ("Education", {"fields": ["college", "theological_seminary"]}),
        ("Service Details", {"fields": ["num_other_churches_served"]}),
    ]

    history_list_display = ["changed_fields"]
