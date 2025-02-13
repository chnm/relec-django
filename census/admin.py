from django import forms
from django.contrib import admin
from django.contrib.admin.widgets import ForeignKeyRawIdWidget
from django.db.models import Count, Q, Sum
from django.http import JsonResponse
from django.urls import path, reverse
from django.utils.html import format_html
from unfold.admin import ModelAdmin, StackedInline, TabularInline

from .models import CensusSchedule, Church, Clergy, Denomination, Location, Membership


class ClergyInline(TabularInline):
    model = Clergy
    extra = 1


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
        "resource_id",
        "schedule_title",
        "denomination",
        "location",
        "total_sunday_school",
        "total_expenditures",
    ]
    list_filter = [
        "denomination"
    ]  # Removed location from list_filter as it might be too heavy
    search_fields = ["schedule_title", "schedule_id", "resource_id"]
    # raw_id_fields = ("location",)  # Add this line to use raw_id_fields
    autocomplete_fields = ["location"]

    readonly_fields = [
        "datascribe_omeka_item_id",
        "datascribe_item_id",
        "datascribe_record_id",
    ]

    fieldsets = [
        (
            "Schedule Information",
            {
                "fields": [
                    "resource_id",
                    "denomination",
                    "schedule_title",
                    "schedule_id",
                    "location",
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
                ],
                "classes": ["collapse"],
            },
        ),
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
        ("Finances", {"fields": ["expenses", "benevolences", "total_expenditures"]}),
    ]
    inlines = [ClergyInline]

    def total_sunday_school(self, obj):
        return obj.sunday_school_num_officers_teachers + obj.sunday_school_num_scholars

    total_sunday_school.short_description = "Total Sunday School"

    history_list_display = ["changed_fields"]


@admin.register(Church)
class ChurchAdmin(ModelAdmin):
    list_display = [
        "name",
        "census_code",
        "location",
        "num_edifices",
        "total_value",
        "has_pastors_residence",
    ]
    list_filter = [
        "division",
        "urban_rural_code",
        "has_pastors_residence",
    ]
    search_fields = ["name", "census_code", "address"]
    autocomplete_fields = ["location"]

    fieldsets = [
        (
            "Church Information",
            {"fields": ["census_record", "name", "census_code", "division"]},
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
        "church",
        "total_members",
        "male_members",
        "female_members",
        "members_under_13",
        "members_13_and_older",
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
