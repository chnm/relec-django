from django.contrib import admin
from church.models import Church, Membership
from finance.models import AnnualFinancialRecord
from education.models import SundaySchool, VacationBibleSchool, ParochialSchool
from clergy.models import Clergy
from location.models import State, County, City
from .models import ReligiousCensusRecord, Denomination

from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.models import User, Group

from unfold.admin import ModelAdmin, StackedInline, TabularInline

# Force User and Group to inherit Unfold styles
admin.site.unregister(User)
admin.site.unregister(Group)


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    pass


@admin.register(Group)
class GroupAdmin(BaseGroupAdmin, ModelAdmin):
    pass


# Registering models:


@admin.register(State)
class StateAdmin(ModelAdmin):
    pass


@admin.register(City)
class CityAdmin(ModelAdmin):
    pass


@admin.register(County)
class CountyAdmin(ModelAdmin):
    pass


@admin.register(Church)
class ChurchAdmin(ModelAdmin):
    pass


class ChurchInline(StackedInline):
    model = Church
    can_delete = False
    max_num = 1


class MembershipAdmin(ModelAdmin):
    pass


class MembershipInline(StackedInline):
    model = Membership
    can_delete = False
    max_num = 1


class FinancialRecordAdmin(ModelAdmin):
    pass


class FinancialRecordInline(StackedInline):
    model = AnnualFinancialRecord
    can_delete = False
    max_num = 1


class SundaySchoolAdmin(ModelAdmin):
    pass


class SundaySchoolInline(StackedInline):
    model = SundaySchool
    can_delete = False
    max_num = 1


class VacationBibleSchoolAdmin(ModelAdmin):
    pass


class VBSInline(StackedInline):
    model = VacationBibleSchool
    can_delete = False
    max_num = 1


class ParochialSchoolAdmin(ModelAdmin):
    pass


class ParochialSchoolInline(StackedInline):
    model = ParochialSchool
    can_delete = False
    max_num = 1


class ClergyAdmin(ModelAdmin):
    pass


class ClergyInline(TabularInline):
    model = Clergy
    extra = 1


@admin.register(ReligiousCensusRecord)
class ReligiousCensusRecordAdmin(ModelAdmin):
    list_display = ("resource_id", "denomination", "schedule_title", "get_church_name")
    list_filter = [
        "denomination",
        ("church_details__state", admin.RelatedOnlyFieldListFilter),
        ("church_details__county", admin.RelatedOnlyFieldListFilter),
    ]
    search_fields = ("resource_id", "church__name", "clergy__name")

    readonly_fields = (
        "datascribe_record_id",
        "datascribe_item_id",
        "datascribe_omeka_item_id",
    )

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "resource_id",
                    "denomination",
                    "schedule_title",
                    "schedule_id",
                )
            },
        ),
        (
            "DataScribe Reference",
            {
                "fields": readonly_fields,
                "classes": ("collapse",),
                "description": "Reference IDs from DataScribe import",
            },
        ),
    )

    inlines = [
        ChurchInline,
        MembershipInline,
        FinancialRecordInline,
        SundaySchoolInline,
        VBSInline,
        ParochialSchoolInline,
        ClergyInline,
    ]

    def get_church_name(self, obj):
        return obj.church.name if hasattr(obj, "church") else "-"

    get_church_name.short_description = "Church Name"

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "resource_id",
                    "denomination",
                    "schedule_title",
                    "schedule_id",
                )
            },
        ),
        (
            "DataScribe Reference",
            {
                "fields": (
                    "datascribe_omeka_item_id",
                    "datascribe_item_id",
                    "datascribe_record_id",
                ),
                "classes": ("collapse",),
            },
        ),
    )


@admin.register(Denomination)
class DenominationAdmin(ModelAdmin):
    list_display = ("name", "code")
    search_fields = ("name", "code")
