import datetime
import os
import re
from collections import defaultdict

import requests
from django import forms
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import path, reverse
from django.utils.html import format_html
from requests.adapters import HTTPAdapter
from requests.exceptions import RequestException
from unfold.admin import ModelAdmin, StackedInline
from urllib3.util.retry import Retry

from .models import CensusSchedule, Clergy, Denomination, Membership, ReligiousBody


class HasLocationFilter(admin.SimpleListFilter):
    """Custom filter to show records with/without locations"""

    title = "Has Location"
    parameter_name = "has_location"

    def lookups(self, request, model_admin):
        return (
            ("yes", "Has Location"),
            ("no", "Missing Location"),
        )

    def queryset(self, request, queryset):
        if self.value() == "yes":
            return queryset.filter(location__isnull=False)
        if self.value() == "no":
            return queryset.filter(location__isnull=True)
        return queryset


class HasCountyFilter(admin.SimpleListFilter):
    """Custom filter to show records with/without county information"""

    title = "Has County"
    parameter_name = "has_county"

    def lookups(self, request, model_admin):
        return (
            ("yes", "Has County"),
            ("no", "Missing County"),
        )

    def queryset(self, request, queryset):
        if self.value() == "yes":
            return queryset.filter(
                location__isnull=False, location__county__isnull=False
            ).exclude(location__county__exact="")
        if self.value() == "no":
            return queryset.filter(
                Q(location__isnull=True)
                | Q(location__county__isnull=True)
                | Q(location__county__exact="")
            )
        return queryset


class CensusScheduleLocationFilter(admin.SimpleListFilter):
    """Custom filter for Census Schedules based on their Religious Body locations"""

    title = "Census Schedule Location Status"
    parameter_name = "schedule_location_status"

    def lookups(self, request, model_admin):
        return (
            ("has_county", "Has County"),
            ("missing_county", "Missing County"),
            ("missing_location", "Missing Location"),
        )

    def queryset(self, request, queryset):
        if self.value() == "has_county":
            return (
                queryset.filter(
                    church_details__location__isnull=False,
                    church_details__location__county__isnull=False,
                )
                .exclude(church_details__location__county__exact="")
                .distinct()
            )
        if self.value() == "missing_county":
            return queryset.filter(
                Q(church_details__location__county__isnull=True)
                | Q(church_details__location__county__exact="")
            ).distinct()
        if self.value() == "missing_location":
            return queryset.filter(church_details__location__isnull=True).distinct()
        return queryset


class TranscriptionWorkflowFilter(admin.SimpleListFilter):
    """Custom filter for common transcription workflow views"""

    title = "Transcription Workflow"
    parameter_name = "workflow_view"

    def lookups(self, request, model_admin):
        return (
            ("unassigned", "📝 Unassigned Records"),
            ("assigned_to_me", "👤 Assigned to Me"),
            ("needs_review", "👀 Needs Review"),
            ("in_progress", "🔄 In Progress"),
            ("completed", "✅ Completed"),
            ("approved", "🎯 Approved"),
        )

    def queryset(self, request, queryset):
        if self.value() == "unassigned":
            return queryset.filter(transcription_status="unassigned")
        elif self.value() == "assigned_to_me":
            return queryset.filter(assigned_transcriber=request.user)
        elif self.value() == "needs_review":
            return queryset.filter(transcription_status="needs_review")
        elif self.value() == "in_progress":
            return queryset.filter(transcription_status="in_progress")
        elif self.value() == "completed":
            return queryset.filter(transcription_status="completed")
        elif self.value() == "approved":
            return queryset.filter(transcription_status="approved")
        return queryset


class AssignmentStatusFilter(admin.SimpleListFilter):
    """Filter for assignment status"""

    title = "Assignment Status"
    parameter_name = "assignment_status"

    def lookups(self, request, model_admin):
        return (
            ("has_transcriber", "Has Transcriber"),
            ("no_transcriber", "No Transcriber"),
            ("has_reviewer", "Has Reviewer"),
            ("no_reviewer", "No Reviewer"),
            ("fully_assigned", "Fully Assigned (Both)"),
            ("unassigned", "Completely Unassigned"),
        )

    def queryset(self, request, queryset):
        if self.value() == "has_transcriber":
            return queryset.filter(assigned_transcriber__isnull=False)
        elif self.value() == "no_transcriber":
            return queryset.filter(assigned_transcriber__isnull=True)
        elif self.value() == "has_reviewer":
            return queryset.filter(assigned_reviewer__isnull=False)
        elif self.value() == "no_reviewer":
            return queryset.filter(assigned_reviewer__isnull=True)
        elif self.value() == "fully_assigned":
            return queryset.filter(
                assigned_transcriber__isnull=False, assigned_reviewer__isnull=False
            )
        elif self.value() == "unassigned":
            return queryset.filter(
                assigned_transcriber__isnull=True, assigned_reviewer__isnull=True
            )
        return queryset


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
    extra = 0  # Changed from 1 to 0 to reduce initial queries
    tab = True
    show_change_link = (
        True  # Add link to edit in separate page instead of loading all data
    )

    def get_queryset(self, request):
        """Optimize queries for clergy inline"""
        qs = super().get_queryset(request)
        return qs.select_related("census_schedule")


class MembershipInline(StackedInline):
    model = Membership
    extra = 0  # Changed from 1 to 0 to reduce initial queries
    tab = True
    autocomplete_fields = ["religious_body"]
    show_change_link = (
        True  # Add link to edit in separate page instead of loading all data
    )

    def get_queryset(self, request):
        """Optimize queries for membership inline"""
        qs = super().get_queryset(request)
        return qs.select_related("census_record", "religious_body")


class ReligiousBodyInline(StackedInline):
    model = ReligiousBody
    raw_id_fields = [
        "location",
    ]
    autocomplete_fields = ["denomination"]
    extra = 0  # Changed from 1 to 0 to reduce initial queries
    tab = True
    show_change_link = (
        True  # Add link to edit in separate page instead of loading all data
    )

    def get_queryset(self, request):
        """Optimize queries for religious body inline"""
        qs = super().get_queryset(request)
        return qs.select_related("census_record", "denomination", "location")

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Cache denomination queryset to avoid repeated database hits"""
        if db_field.name == "denomination":
            # Cache the queryset to prevent multiple loads
            if not hasattr(self, "_denomination_queryset"):
                self._denomination_queryset = Denomination.objects.all().order_by(
                    "name"
                )
            kwargs["queryset"] = self._denomination_queryset
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


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
    search_fields = ["name", "denomination_id", "family_census", "family_relec"]
    ordering = ["name"]
    list_filter = ["family_census", "family_relec"]
    actions = [sync_denominations]

    # Add history view
    history_list_display = ["changed_fields"]

    def get_search_results(self, request, queryset, search_term):
        """Optimize autocomplete search"""
        queryset, use_distinct = super().get_search_results(
            request, queryset, search_term
        )
        # Limit autocomplete results for performance
        if "autocomplete" in request.path:
            queryset = queryset[:50]
        return queryset, use_distinct


# Status change actions
def mark_unassigned(modeladmin, request, queryset):
    """Mark records as unassigned"""
    count = queryset.update(
        transcription_status="unassigned", assigned_transcriber=None
    )
    modeladmin.message_user(request, f"{count} records marked as unassigned.")


mark_unassigned.short_description = "Mark as unassigned"


def mark_assigned(modeladmin, request, queryset):
    """Mark records as assigned (keeps current transcriber)"""
    count = queryset.update(transcription_status="assigned")
    modeladmin.message_user(request, f"{count} records marked as assigned.")


mark_assigned.short_description = "Mark as assigned"


def mark_in_progress(modeladmin, request, queryset):
    """Mark records as in progress"""
    count = queryset.update(transcription_status="in_progress")
    modeladmin.message_user(request, f"{count} records marked as in progress.")


mark_in_progress.short_description = "Mark as in progress"


def mark_needs_review(modeladmin, request, queryset):
    """Admin action to mark records as needing review"""
    count = queryset.update(transcription_status="needs_review")
    modeladmin.message_user(request, f"{count} records marked as needing review.")


mark_needs_review.short_description = "Mark as needs review"


def mark_completed(modeladmin, request, queryset):
    """Mark records as transcribed/completed"""
    count = queryset.update(transcription_status="completed")
    modeladmin.message_user(request, f"{count} records marked as transcribed.")


mark_completed.short_description = "Mark as transcribed"


def mark_approved(modeladmin, request, queryset):
    """Admin action to approve transcribed records"""
    count = queryset.update(transcription_status="approved")
    modeladmin.message_user(request, f"{count} records approved.")


mark_approved.short_description = "Mark as approved"


# Assignment actions
def assign_to_me(modeladmin, request, queryset):
    """Admin action to assign records to current user"""
    if request.user.groups.filter(name="Transcribers").exists():
        count = queryset.update(
            assigned_transcriber=request.user, transcription_status="assigned"
        )
        modeladmin.message_user(
            request, f"{count} records assigned to you for transcription."
        )
    elif (
        request.user.groups.filter(name="Reviewers").exists()
        or request.user.is_superuser
    ):
        count = queryset.update(assigned_reviewer=request.user)
        modeladmin.message_user(request, f"{count} records assigned to you for review.")
    else:
        modeladmin.message_user(
            request, "You don't have permission to assign records.", level="ERROR"
        )


assign_to_me.short_description = "Assign selected items to me"


def unassign_transcriber(modeladmin, request, queryset):
    """Remove transcriber assignment"""
    count = queryset.update(assigned_transcriber=None)
    modeladmin.message_user(request, f"Transcriber removed from {count} records.")


unassign_transcriber.short_description = "Remove transcriber assignment"


def unassign_reviewer(modeladmin, request, queryset):
    """Remove reviewer assignment"""
    count = queryset.update(assigned_reviewer=None)
    modeladmin.message_user(request, f"Reviewer removed from {count} records.")


unassign_reviewer.short_description = "Remove reviewer assignment"


class BulkAssignForm(forms.Form):
    """Form for bulk assignment of users to records"""

    transcriber = forms.ModelChoiceField(
        queryset=User.objects.filter(groups__name="Transcribers"),
        required=False,
        empty_label="-- Select Transcriber --",
        help_text="Assign a transcriber to selected records",
    )
    reviewer = forms.ModelChoiceField(
        queryset=User.objects.filter(groups__name="Reviewers"),
        required=False,
        empty_label="-- Select Reviewer --",
        help_text="Assign a reviewer to selected records",
    )
    status = forms.ChoiceField(
        choices=[("", "-- No Status Change --")]
        + CensusSchedule.TRANSCRIPTION_STATUS_CHOICES,
        required=False,
        help_text="Optionally change status for selected records",
    )


def bulk_assign_users(modeladmin, request, queryset):
    """Advanced bulk assignment action"""
    if request.POST.get("apply"):
        form = BulkAssignForm(request.POST)
        if form.is_valid():
            transcriber = form.cleaned_data["transcriber"]
            reviewer = form.cleaned_data["reviewer"]
            status = form.cleaned_data["status"]

            update_data = {}
            if transcriber:
                update_data["assigned_transcriber"] = transcriber
            if reviewer:
                update_data["assigned_reviewer"] = reviewer
            if status:
                update_data["transcription_status"] = status

            if update_data:
                count = queryset.update(**update_data)
                messages.success(request, f"Successfully updated {count} records.")
                # Redirect back to the changelist with success message
                return HttpResponseRedirect(
                    reverse("admin:census_censusschedule_changelist")
                )
            else:
                messages.warning(request, "No changes specified.")
        else:
            # Form has validation errors
            messages.error(request, "Please correct the errors below.")
    else:
        form = BulkAssignForm()

    return render(
        request,
        "admin/census/bulk_assign.html",
        {
            "form": form,
            "objects": queryset,
            "opts": modeladmin.model._meta,
            "title": "Bulk Assign Users and Status",
        },
    )


bulk_assign_users.short_description = "Bulk assign users/status to selected records"


@admin.register(CensusSchedule)
class CensusScheduleAdmin(ModelAdmin):
    list_display = [
        "schedule_title",
        "schedule_id",
        "resource_id",
        "transcription_status_display",
        "assigned_transcriber",
        "assigned_reviewer",
    ]
    search_fields = ["schedule_title", "schedule_id", "resource_id"]
    list_filter = [
        TranscriptionWorkflowFilter,
        "transcription_status",
        AssignmentStatusFilter,
        "assigned_transcriber",
        "assigned_reviewer",
        CensusScheduleLocationFilter,
    ]
    actions = [
        # Status changes
        mark_unassigned,
        mark_assigned,
        mark_in_progress,
        mark_needs_review,
        mark_completed,
        mark_approved,
        # Assignments
        assign_to_me,
        unassign_transcriber,
        unassign_reviewer,
        bulk_assign_users,
    ]

    def get_urls(self):
        """Add custom URLs for data analysis"""
        urls = super().get_urls()
        custom_urls = [
            path(
                "schedule-gap-analysis/",
                self.admin_site.admin_view(self.schedule_gap_analysis_view),
                name="census_schedule_gap_analysis",
            ),
            path(
                "missing-county-analysis/",
                self.admin_site.admin_view(self.missing_county_analysis_view),
                name="census_schedule_missing_county_analysis",
            ),
        ]
        return custom_urls + urls

    def schedule_gap_analysis_view(self, request):
        """View to analyze gaps in schedule IDs by denomination"""
        # Get all census schedules with their related religious bodies
        schedules_with_denominations = (
            CensusSchedule.objects.select_related()
            .prefetch_related("church_details__denomination")
            .filter(church_details__isnull=False)
            .distinct()
        )

        # Group by denomination and analyze gaps
        denomination_gaps = defaultdict(
            lambda: {
                "schedules": [],
                "gaps": [],
                "denomination_name": "",
                "total_count": 0,
            }
        )

        for schedule in schedules_with_denominations:
            for religious_body in schedule.church_details.all():
                if religious_body.denomination:
                    denom_id = religious_body.denomination.id
                    denomination_gaps[denom_id]["denomination_name"] = (
                        religious_body.denomination.name
                    )
                    denomination_gaps[denom_id]["schedules"].append(
                        {
                            "schedule_id": schedule.schedule_id,
                            "schedule_title": schedule.schedule_title,
                            "resource_id": schedule.resource_id,
                        }
                    )

        # Analyze gaps for each denomination
        gap_analysis = []
        for denom_id, data in denomination_gaps.items():
            schedules = data["schedules"]
            denomination_name = data["denomination_name"]

            # Extract numeric parts from schedule IDs and sort
            numeric_ids = []
            non_numeric_ids = []

            for schedule in schedules:
                schedule_id = schedule["schedule_id"]
                # Try to extract numbers from schedule ID
                numbers = re.findall(r"\d+", schedule_id)
                if numbers:
                    # Take the first/main number found
                    numeric_ids.append(
                        {
                            "numeric_id": int(numbers[0]),
                            "original_id": schedule_id,
                            "schedule": schedule,
                        }
                    )
                else:
                    non_numeric_ids.append(schedule)

            # Sort by numeric ID
            numeric_ids.sort(key=lambda x: x["numeric_id"])

            # Find gaps in the sequence
            gaps = []
            if len(numeric_ids) > 1:
                for i in range(len(numeric_ids) - 1):
                    current = numeric_ids[i]["numeric_id"]
                    next_id = numeric_ids[i + 1]["numeric_id"]
                    if next_id - current > 1:
                        gaps.append(
                            {
                                "after": current,
                                "before": next_id,
                                "missing_range": list(range(current + 1, next_id)),
                            }
                        )

            gap_analysis.append(
                {
                    "denomination_name": denomination_name,
                    "denomination_id": denom_id,
                    "total_schedules": len(schedules),
                    "numeric_schedules": len(numeric_ids),
                    "non_numeric_schedules": len(non_numeric_ids),
                    "sorted_schedules": numeric_ids,
                    "non_numeric_ids": non_numeric_ids,
                    "gaps": gaps,
                    "gap_count": len(gaps),
                }
            )

        # Sort by denomination name
        gap_analysis.sort(key=lambda x: x["denomination_name"])

        context = {
            "title": "Schedule ID Gap Analysis by Denomination",
            "gap_analysis": gap_analysis,
            "opts": self.model._meta,
        }

        return render(request, "admin/census/schedule_gap_analysis.html", context)

    def missing_county_analysis_view(self, request):
        """View to analyze census schedules missing county information"""

        # Get all census schedules with their religious body relationships
        all_schedules = CensusSchedule.objects.select_related().prefetch_related(
            "church_details__denomination", "church_details__location"
        )

        # Categorize schedules by location status
        schedules_with_county = []
        schedules_missing_location = []
        schedules_missing_county = []
        schedules_with_blank_county = []

        # Group by state for easier analysis
        state_analysis = defaultdict(
            lambda: {
                "state_name": "",
                "total_schedules": 0,
                "with_county": 0,
                "missing_location": 0,
                "missing_county": 0,
                "blank_county": 0,
                "counties_represented": set(),
                "schedules_by_county": defaultdict(list),
            }
        )

        no_state_schedules = {
            "missing_location": [],
            "missing_county": [],
            "blank_county": [],
        }

        for schedule in all_schedules:
            has_location = False
            has_county = False
            state_code = None
            county_name = None

            # Check through all religious bodies for this schedule
            for religious_body in schedule.church_details.all():
                if religious_body.location:
                    has_location = True
                    state_code = religious_body.location.state
                    county_name = religious_body.location.county

                    if county_name and county_name.strip():
                        has_county = True
                        schedules_with_county.append(
                            {
                                "schedule": schedule,
                                "location": religious_body.location,
                                "county": county_name,
                            }
                        )
                        # Add to state analysis
                        state_analysis[state_code]["state_name"] = state_code
                        state_analysis[state_code]["with_county"] += 1
                        state_analysis[state_code]["counties_represented"].add(
                            county_name
                        )
                        state_analysis[state_code]["schedules_by_county"][
                            county_name
                        ].append(schedule)
                    else:
                        # Has location but county is null/blank
                        if county_name is None:
                            schedules_missing_county.append(
                                {
                                    "schedule": schedule,
                                    "location": religious_body.location,
                                    "issue": "County field is null",
                                }
                            )
                        else:
                            schedules_with_blank_county.append(
                                {
                                    "schedule": schedule,
                                    "location": religious_body.location,
                                    "issue": "County field is empty string",
                                }
                            )
                    break  # Only need to check first religious body with location

            # Update state totals
            if state_code:
                state_analysis[state_code]["total_schedules"] += 1
                if not has_location:
                    state_analysis[state_code]["missing_location"] += 1
                elif not has_county:
                    if county_name is None:
                        state_analysis[state_code]["missing_county"] += 1
                    else:
                        state_analysis[state_code]["blank_county"] += 1
            else:
                # No state information available
                if not has_location:
                    schedules_missing_location.append(
                        {
                            "schedule": schedule,
                            "issue": "No location assigned to religious body",
                        }
                    )
                    no_state_schedules["missing_location"].append(schedule)
                elif not has_county:
                    if county_name is None:
                        no_state_schedules["missing_county"].append(schedule)
                    else:
                        no_state_schedules["blank_county"].append(schedule)

        # Convert state analysis to list and sort
        state_summary = []
        for state_code, data in state_analysis.items():
            data["counties_represented"] = list(data["counties_represented"])
            data["counties_represented"].sort()
            data["county_count"] = len(data["counties_represented"])
            state_summary.append(data)

        state_summary.sort(key=lambda x: x["state_name"])

        # Overall statistics
        total_schedules = all_schedules.count()
        total_with_county = len(schedules_with_county)
        total_missing_location = len(schedules_missing_location)
        total_missing_county = len(schedules_missing_county)
        total_blank_county = len(schedules_with_blank_county)
        total_issues = (
            total_missing_location + total_missing_county + total_blank_county
        )

        context = {
            "title": "Missing County Analysis",
            "total_schedules": total_schedules,
            "total_with_county": total_with_county,
            "total_missing_location": total_missing_location,
            "total_missing_county": total_missing_county,
            "total_blank_county": total_blank_county,
            "total_issues": total_issues,
            "completion_percentage": round(
                (total_with_county / total_schedules) * 100, 1
            )
            if total_schedules > 0
            else 0,
            "state_summary": state_summary,
            "schedules_missing_location": schedules_missing_location[
                :50
            ],  # Limit for performance
            "schedules_missing_county": schedules_missing_county[:50],
            "schedules_with_blank_county": schedules_with_blank_county[:50],
            "no_state_schedules": no_state_schedules,
            "opts": self.model._meta,
        }

        return render(request, "admin/census/missing_county_analysis.html", context)

    readonly_fields = [
        "datascribe_omeka_item_id",
        "datascribe_item_id",
        "datascribe_record_id",
        "datascribe_original_image_path",
        "omeka_storage_id",
        # "image_preview",
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
            "Project Management",
            {
                "fields": [
                    "transcription_status",
                    "assigned_transcriber",
                    "assigned_reviewer",
                    "transcription_notes",
                ]
            },
        ),
        (
            "Image",
            {
                "fields": [
                    "original_image",
                    # "image_preview",
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

    def transcription_status_display(self, obj):
        """Display status with color coding"""
        color = obj.get_status_display_color()
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_transcription_status_display(),
        )

    transcription_status_display.short_description = "Status"

    def get_queryset(self, request):
        """Filter records based on user permissions and optimize queries"""
        qs = super().get_queryset(request)

        # Optimize foreign key lookups
        qs = qs.select_related("assigned_transcriber", "assigned_reviewer")

        # Prefetch related inlines to reduce queries
        qs = qs.prefetch_related(
            "church_details",
            "church_details__denomination",
            "church_details__location",
            "membership_details",
            "membership_details__religious_body",
            "clergy",
        )

        # If user is ONLY in Transcribers group (student transcriber), only show their assigned records
        # Superusers and users in multiple groups (like admins) see all records
        user_groups = list(request.user.groups.values_list("name", flat=True))

        if (
            request.user.groups.filter(name="Transcribers").exists()
            and not request.user.is_superuser
            and user_groups == ["Transcribers"]
        ):  # Only in Transcribers group
            return qs.filter(assigned_transcriber=request.user)

        return qs

    def has_delete_permission(self, request, obj=None):
        """Students cannot delete records"""
        if request.user.groups.filter(name="Transcribers").exists():
            return False
        return super().has_delete_permission(request, obj)

    def save_model(self, request, obj, form, change):
        """Auto-set status when students save their work"""
        if request.user.groups.filter(name="Transcribers").exists():
            # If student is saving and there are related objects, mark as needs review
            # Use count() instead of exists() to utilize prefetched data
            if change and (
                obj.church_details.count() > 0
                or obj.membership_details.count() > 0
                or obj.clergy.count() > 0
            ):
                obj.transcription_status = "needs_review"

        super().save_model(request, obj, form, change)

    # def image_thumbnail(self, obj):
    #     """Display small thumbnail in list view"""
    #     if obj.original_image:
    #         try:
    #             return format_html(
    #                 '<img src="{}" style="width: 50px; height: 38px; object-fit: cover;" />',
    #                 obj.admin_thumbnail.url
    #             )
    #         except:
    #             return "Image error"
    #     return "No image"
    # image_thumbnail.short_description = "Image"

    # def image_preview(self, obj):
    #     """Display medium-sized preview in detail view"""
    #     if obj.original_image:
    #         try:
    #             return format_html(
    #                 '<img src="{}" style="max-width: 400px; max-height: 300px;" /><br>'
    #                 '<a href="{}" target="_blank">View full size</a>',
    #                 obj.thumbnail_medium.url,
    #                 obj.original_image.url
    #             )
    #         except:
    #             return format_html(
    #                 '<a href="{}" target="_blank">View image</a><br>'
    #                 '(Thumbnail generation failed)',
    #                 obj.original_image.url
    #             )
    #     return "No image uploaded"
    # image_preview.short_description = "Image Preview"

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

    def get_queryset(self, request):
        """Optimize queries for list display"""
        qs = super().get_queryset(request)
        return qs.select_related("census_schedule")

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
    list_display = [
        "name",
        "denomination",
        "census_record",
        "location",
        "num_edifices",
        "edifice_value",
    ]
    list_filter = [
        "denomination",
        "location__state",
        HasLocationFilter,
        HasCountyFilter,
    ]
    search_fields = ["name", "denomination__name", "census_record__schedule_title"]
    raw_id_fields = ["location"]
    autocomplete_fields = ["denomination"]

    def get_queryset(self, request):
        """Optimize queries for list display"""
        qs = super().get_queryset(request)
        return qs.select_related("denomination", "census_record", "location")

    def get_search_results(self, request, queryset, search_term):
        """Optimize autocomplete search"""
        queryset, use_distinct = super().get_search_results(
            request, queryset, search_term
        )
        # Limit autocomplete results for performance
        if "autocomplete" in request.path:
            queryset = queryset[:50]
        return queryset, use_distinct

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
            "Location",
            {
                "fields": [
                    "address",
                    "location",
                    "urban_rural_code",
                ]
            },
        ),
        (
            "Property Details",
            {
                "fields": [
                    "num_edifices",
                    "edifice_value",
                    "edifice_debt",
                    "has_pastors_residence",
                    "residence_value",
                    "residence_debt",
                ]
            },
        ),
        (
            "Finances",
            {
                "fields": [
                    "expenses",
                    "benevolences",
                    "total_expenditures",
                ]
            },
        ),
    ]

    history_list_display = ["changed_fields"]


@admin.register(Membership)
class MembershipAdmin(ModelAdmin):
    list_display = [
        "religious_body",
        "census_record",
        "total_members_by_sex",
        "total_members_by_age",
        "male_members",
        "female_members",
    ]
    list_filter = ["census_record__transcription_status"]
    search_fields = ["religious_body__name", "census_record__schedule_title"]

    def get_queryset(self, request):
        """Optimize queries for list display"""
        qs = super().get_queryset(request)
        return qs.select_related("religious_body", "census_record")

    fieldsets = [
        (
            "Record Information",
            {
                "fields": [
                    "census_record",
                    "religious_body",
                ]
            },
        ),
        (
            "Membership by Gender",
            {
                "fields": [
                    "male_members",
                    "female_members",
                    "total_members_by_sex",
                ]
            },
        ),
        (
            "Membership by Age",
            {
                "fields": [
                    "members_under_13",
                    "members_13_and_older",
                    "total_members_by_age",
                ]
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
            {
                "fields": [
                    "vbs_num_officers_teachers",
                    "vbs_num_scholars",
                ]
            },
        ),
        (
            "Weekday Religious School",
            {
                "fields": [
                    "weekday_num_officers_teachers",
                    "weekday_num_scholars",
                ]
            },
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

    history_list_display = ["changed_fields"]
