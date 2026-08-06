import datetime
import os
import re
from collections import defaultdict

import requests
from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.contrib.admin import helpers
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, models
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html
from import_export.admin import ImportExportModelAdmin
from requests.adapters import HTTPAdapter
from requests.exceptions import RequestException
from unfold.admin import ModelAdmin, StackedInline
from unfold.contrib.import_export.forms import ExportForm, ImportForm
from urllib3.util.retry import Retry

from location.models import PopulatedPlace

from .models import (
    CensusSchedule,
    Clergy,
    Denomination,
    DenominationCensusReport,
    Membership,
    ReligiousBody,
    ScheduleTranscription,
    TranscriptionBatch,
    TranscriptionJob,
    TranscriptionRun,
)
from .resources import CensusScheduleResource, DenominationResource
from .transcription.comparison import build_comparison, source_raw_json
from .transcription.services import LaunchError, launch_transcription_run
from .workflow import (
    LOCKED_FOR_TRANSCRIBERS,
    TRANSCRIBER_ACTIONS,
    is_reviewer,
    is_transcriber_only,
    schedules_with_religious_bodies,
)


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
            return queryset.filter(census_record__populated_place__isnull=False)
        if self.value() == "no":
            return queryset.filter(census_record__populated_place__isnull=True)
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
            return queryset.filter(census_record__county__isnull=False)
        if self.value() == "no":
            return queryset.filter(census_record__county__isnull=True)
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
            return queryset.filter(county__isnull=False)
        if self.value() == "missing_county":
            return queryset.filter(county__isnull=True)
        if self.value() == "missing_location":
            return queryset.filter(county__isnull=True, populated_place__isnull=True)
        return queryset


class TranscriptionWorkflowFilter(admin.SimpleListFilter):
    """Custom filter for common transcription workflow views"""

    title = "Transcription Workflow"
    parameter_name = "workflow_view"

    def lookups(self, request, model_admin):
        return (
            ("unassigned", "Unassigned Records"),
            ("assigned_to_me", "Assigned to Me"),
            ("review_queue", "Review Queue"),
            ("needs_review", "Imported - Needs Review"),
            ("in_progress", "In Progress"),
            ("completed", "Student Work - Ready for Review"),
            ("approved", "Approved"),
        )

    def queryset(self, request, queryset):
        if self.value() == "unassigned":
            return queryset.filter(transcription_status="unassigned")
        elif self.value() == "assigned_to_me":
            return queryset.filter(assigned_transcriber=request.user)
        elif self.value() == "review_queue":
            return queryset.filter(
                transcription_status__in=["needs_review", "completed"]
            )
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
    autocomplete_fields = ["denomination"]
    extra = 0  # Changed from 1 to 0 to reduce initial queries
    tab = True
    show_change_link = (
        True  # Add link to edit in separate page instead of loading all data
    )

    # Only show fields relevant to the religious body itself
    # Location is now tracked at the CensusSchedule level
    fields = [
        "name",
        "denomination",
        "census_code",
        "division",
        "address",
        "urban_rural_code",
        "num_edifices",
        "edifice_value",
        "edifice_debt",
        "has_pastors_residence",
        "residence_value",
        "residence_debt",
        "expenses",
        "benevolences",
        "total_expenditures",
    ]

    def get_queryset(self, request):
        """Optimize queries for religious body inline"""
        qs = super().get_queryset(request)
        return qs.select_related("census_record", "denomination")

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


class ScheduleTranscriptionInline(StackedInline):
    model = ScheduleTranscription
    extra = 0
    tab = True
    fields = ["run", "data", "created_at"]
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("run")


class ReviewerReadOnlyModelAdmin(ModelAdmin):
    """Expose orchestration evidence to reviewers without mutation rights."""

    def has_module_permission(self, request):
        return is_reviewer(request.user)

    def has_view_permission(self, request, obj=None):
        return is_reviewer(request.user)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(TranscriptionRun)
class TranscriptionRunAdmin(ReviewerReadOnlyModelAdmin):
    list_display = ["key", "kind", "job_summary", "token_summary", "created_at"]
    list_filter = ["kind"]
    search_fields = ["key"]
    readonly_fields = ["key", "kind", "metadata", "created_at", "token_usage"]

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .annotate(
                job_count=models.Count("transcription_jobs"),
                aggregate_input_tokens=models.Sum("transcription_jobs__input_tokens"),
                aggregate_cache_creation_tokens=models.Sum(
                    "transcription_jobs__cache_creation_input_tokens"
                ),
                aggregate_cache_read_tokens=models.Sum(
                    "transcription_jobs__cache_read_input_tokens"
                ),
                aggregate_output_tokens=models.Sum("transcription_jobs__output_tokens"),
            )
        )

    @admin.display(description="Jobs")
    def job_summary(self, obj):
        return obj.job_count

    @admin.display(description="Tokens")
    def token_summary(self, obj):
        total_input = sum(
            value or 0
            for value in (
                obj.aggregate_input_tokens,
                obj.aggregate_cache_creation_tokens,
                obj.aggregate_cache_read_tokens,
            )
        )
        return f"in {total_input:,} / " f"out {obj.aggregate_output_tokens or 0:,}"


@admin.register(TranscriptionBatch)
class TranscriptionBatchAdmin(ReviewerReadOnlyModelAdmin):
    list_display = [
        "id",
        "run",
        "state",
        "provider_batch_id",
        "request_count",
        "submitted_at",
        "collected_at",
    ]
    list_filter = ["state", "provider"]
    search_fields = ["provider_batch_id", "run__key"]
    readonly_fields = [field.name for field in TranscriptionBatch._meta.fields]


@admin.register(TranscriptionJob)
class TranscriptionJobAdmin(ReviewerReadOnlyModelAdmin):
    list_display = [
        "custom_id",
        "census_schedule",
        "run",
        "state",
        "total_input_tokens_display",
        "output_tokens",
        "completed_at",
    ]
    list_filter = ["state", "run"]
    search_fields = [
        "custom_id",
        "census_schedule__schedule_id",
        "census_schedule__schedule_title",
        "run__key",
    ]
    readonly_fields = [field.name for field in TranscriptionJob._meta.fields]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("census_schedule", "run")

    @admin.display(description="Input tokens")
    def total_input_tokens_display(self, obj):
        return obj.total_input_tokens


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


class DenominationCensusReportInline(StackedInline):
    model = DenominationCensusReport
    extra = 0
    readonly_fields = ["omeka_item_id", "omeka_media_id", "original_filename"]
    fields = [
        "title",
        "pdf_file",
        "original_filename",
        "omeka_item_id",
        "omeka_media_id",
    ]


@admin.register(Denomination)
class DenominationAdmin(ImportExportModelAdmin, ModelAdmin):
    import_form_class = ImportForm
    export_form_class = ExportForm
    resource_classes = [DenominationResource]
    list_display = [
        "name",
        "denomination_id",
        "family_relec",
        "family_census",
        "published_churches_count",
    ]
    search_fields = [
        "name",
        "short_name",
        "denomination_id",
        "family_relec",
        "family_census",
    ]
    ordering = ["name"]
    list_filter = ["family_relec", "family_census"]
    actions = [sync_denominations]
    inlines = [DenominationCensusReportInline]

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
    """Mark imported or untriaged records as needing review."""
    eligible = schedules_with_religious_bodies(queryset)
    count = eligible.update(transcription_status="needs_review")
    skipped = queryset.count() - count
    modeladmin.message_user(request, f"{count} records marked as needing review.")
    if skipped:
        modeladmin.message_user(
            request,
            f"{skipped} records skipped because they have no religious body.",
            level=messages.WARNING,
        )


mark_needs_review.short_description = "Mark imported records as needs review"


def mark_completed(modeladmin, request, queryset):
    """Submit completed student transcriptions for PI review."""
    eligible = schedules_with_religious_bodies(queryset)
    count = eligible.update(transcription_status="completed")
    skipped = queryset.count() - count
    modeladmin.message_user(request, f"{count} records marked as ready for review.")
    if skipped:
        modeladmin.message_user(
            request,
            f"{skipped} records skipped because they have no religious body.",
            level=messages.WARNING,
        )


mark_completed.short_description = "Mark as ready for review"


def mark_approved(modeladmin, request, queryset):
    """Admin action to approve transcribed records"""
    count = queryset.update(transcription_status="approved")
    modeladmin.message_user(request, f"{count} records approved.")


mark_approved.short_description = "Mark as approved"


# Assignment actions
def assign_to_me(modeladmin, request, queryset):
    """Admin action to assign records to current user"""
    if is_transcriber_only(request.user):
        count = queryset.update(
            assigned_transcriber=request.user, transcription_status="assigned"
        )
        modeladmin.message_user(
            request, f"{count} records assigned to you for transcription."
        )
    elif is_reviewer(request.user):
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


class ClaudeTranscriptionRunForm(forms.Form):
    run_key = forms.SlugField(
        max_length=120,
        help_text="A permanent provenance key; it cannot be renamed later.",
    )
    model = forms.ChoiceField()
    limit = forms.IntegerField(min_value=1)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["model"].choices = [
            (model, model) for model in settings.CLAUDE_TRANSCRIPTION_MODELS
        ]
        self.fields["limit"].max_value = settings.CLAUDE_TRANSCRIPTION_MAX_RUN_LIMIT
        self.fields["limit"].initial = settings.CLAUDE_TRANSCRIPTION_DEFAULT_RUN_LIMIT


@admin.action(description="Queue selected schedules for Claude transcription")
def queue_claude_transcription(modeladmin, request, queryset):
    if not is_reviewer(request.user):
        modeladmin.message_user(
            request,
            "Only reviewers can launch paid transcription runs.",
            level=messages.ERROR,
        )
        return HttpResponseRedirect(reverse("admin:census_censusschedule_changelist"))

    initial = {
        "run_key": timezone.now().strftime("claude-%Y%m%d-%H%M%S"),
        "model": settings.CLAUDE_TRANSCRIPTION_MODELS[0],
        "limit": settings.CLAUDE_TRANSCRIPTION_DEFAULT_RUN_LIMIT,
    }
    form = ClaudeTranscriptionRunForm(
        request.POST if request.POST.get("apply") else None,
        initial=initial,
    )
    if request.POST.get("apply") and form.is_valid():
        try:
            run = launch_transcription_run(
                queryset=queryset,
                key=form.cleaned_data["run_key"],
                model=form.cleaned_data["model"],
                limit=form.cleaned_data["limit"],
                user=request.user,
            )
        except (LaunchError, ValidationError, IntegrityError) as exc:
            form.add_error(None, str(exc))
        else:
            modeladmin.message_user(
                request,
                f"Queued {run.metadata['schedule_count']} schedules in run {run.key}.",
            )
            return HttpResponseRedirect(
                reverse("admin:census_transcriptionrun_change", args=[run.pk])
            )

    selected = request.POST.getlist(helpers.ACTION_CHECKBOX_NAME)
    eligible_count = (
        queryset.exclude(original_image="").exclude(original_image__isnull=True).count()
    )
    return render(
        request,
        "admin/census/queue-claude-transcription.html",
        {
            "form": form,
            "objects": queryset[:100],
            "selected": selected,
            "selected_count": queryset.count(),
            "eligible_count": eligible_count,
            "opts": modeladmin.model._meta,
            "title": "Queue Claude transcription run",
            "api_configured": bool(settings.ANTHROPIC_API_KEY),
            "transcription_enabled": settings.CLAUDE_TRANSCRIPTION_ENABLED,
            "prompt_version": "relec-1926-v1",
        },
    )


@admin.register(CensusSchedule)
class CensusScheduleAdmin(ModelAdmin):
    change_form_template = "admin/census/censusschedule/change_form.html"
    list_display = [
        "schedule_title",
        "schedule_id",
        "resource_id",
        "get_location_display",
        "transcription_status_display",
        "assigned_transcriber",
        "assigned_reviewer",
    ]
    search_fields = [
        "schedule_title",
        "schedule_id",
        "resource_id",
        "county__name",
        "county__state__name",
        "county__state__code",
        "populated_place__name",
        "schedule_denomination__name",
        "schedule_denomination__short_name",
        "assigned_transcriber__username",
        "assigned_transcriber__first_name",
        "assigned_transcriber__last_name",
        "assigned_reviewer__username",
        "assigned_reviewer__first_name",
        "assigned_reviewer__last_name",
        "transcription_notes",
    ]
    list_filter = [
        TranscriptionWorkflowFilter,
        "transcription_status",
        AssignmentStatusFilter,
        "assigned_transcriber",
        "assigned_reviewer",
        "county__state",
        "schedule_denomination",
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
        queue_claude_transcription,
    ]
    ordering = ["schedule_title"]

    class Media:
        js = ["js/admin_cascade_populated_place.js"]

    def get_actions(self, request):
        actions = super().get_actions(request)
        if is_transcriber_only(request.user):
            actions = {
                name: action
                for name, action in actions.items()
                if name in TRANSCRIBER_ACTIONS
            }
        return actions

    def get_readonly_fields(self, request, obj=None):
        readonly_fields = list(super().get_readonly_fields(request, obj))
        if is_transcriber_only(request.user):
            readonly_fields.extend(
                [
                    "transcription_status",
                    "assigned_transcriber",
                    "assigned_reviewer",
                ]
            )
        return readonly_fields

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
            path(
                "location-export/",
                self.admin_site.admin_view(self.location_export_view),
                name="census_schedule_location_export",
            ),
            path(
                "<path:object_id>/compare-transcriptions/",
                self.admin_site.admin_view(self.compare_transcriptions_view),
                name="census_censusschedule_compare_transcriptions",
            ),
        ]
        return custom_urls + urls

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        extra_context = extra_context or {}
        extra_context["show_transcription_comparison"] = bool(
            object_id
            and is_reviewer(request.user)
            and ScheduleTranscription.objects.filter(
                census_schedule_id=object_id
            ).exists()
        )
        return super().changeform_view(
            request,
            object_id=object_id,
            form_url=form_url,
            extra_context=extra_context,
        )

    def compare_transcriptions_view(self, request, object_id):
        """Compare immutable human and agent outputs without changing either."""
        if not is_reviewer(request.user):
            raise PermissionDenied

        schedule = get_object_or_404(
            CensusSchedule.objects.select_related(
                "county__state",
                "populated_place__county__state",
                "schedule_denomination",
            ),
            pk=object_id,
        )
        transcriptions = list(
            schedule.transcriptions.select_related("run").order_by(
                "-created_at", "-pk"
            )
        )
        human_sources = [
            source for source in transcriptions if source.run.kind == "human_snapshot"
        ]
        agent_sources = [
            source for source in transcriptions if source.run.kind == "agent"
        ]
        human_source = self._comparison_source(
            human_sources, request.GET.get("human")
        )
        agent_source = self._comparison_source(
            agent_sources, request.GET.get("agent")
        )

        jobs = {
            job.run_id: job
            for job in schedule.transcription_jobs.filter(
                state=TranscriptionJob.State.SUCCEEDED
            ).select_related("run")
        }
        comparison = build_comparison(
            human_source.data if human_source else None,
            agent_source.data if agent_source else None,
        )
        try:
            image_url = schedule.original_image.url if schedule.original_image else ""
        except ValueError:
            image_url = ""

        context = {
            **self.admin_site.each_context(request),
            "title": f"Compare transcriptions: {schedule}",
            "opts": self.model._meta,
            "schedule": schedule,
            "image_url": image_url,
            "human_sources": human_sources,
            "agent_sources": agent_sources,
            "human_source": self._comparison_source_details(
                human_source, jobs.get(human_source.run_id) if human_source else None
            ),
            "agent_source": self._comparison_source_details(
                agent_source, jobs.get(agent_source.run_id) if agent_source else None
            ),
            "comparison": comparison,
        }
        return render(
            request,
            "admin/census/censusschedule/compare-transcriptions.html",
            context,
        )

    @staticmethod
    def _comparison_source(sources, requested_id):
        if requested_id:
            selected = next(
                (source for source in sources if str(source.pk) == requested_id),
                None,
            )
            if selected:
                return selected
        return sources[0] if sources else None

    @staticmethod
    def _comparison_source_details(source, job):
        if source is None:
            return None
        metadata = source.run.metadata
        return {
            "object": source,
            "run": source.run,
            "model": metadata.get("model", ""),
            "contract_version": metadata.get("contract_version", ""),
            "job": job,
            "raw_json": source_raw_json(source),
        }

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
                    denomination_gaps[denom_id][
                        "denomination_name"
                    ] = religious_body.denomination.name
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

        # Get all census schedules with their location hierarchy
        all_schedules = CensusSchedule.objects.select_related(
            "county__state", "populated_place"
        ).prefetch_related("church_details__denomination")

        # Categorize schedules by location status
        schedules_with_county = []
        schedules_missing_location = []
        schedules_missing_county = []

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
            if schedule.county:
                state_code = (
                    schedule.county.state.code if schedule.county.state else None
                )
                county_name = schedule.county.name

                schedules_with_county.append(
                    {
                        "schedule": schedule,
                        "county": county_name,
                    }
                )

                if state_code:
                    state_analysis[state_code]["state_name"] = state_code
                    state_analysis[state_code]["with_county"] += 1
                    state_analysis[state_code]["counties_represented"].add(county_name)
                    state_analysis[state_code]["schedules_by_county"][
                        county_name
                    ].append(schedule)
                    state_analysis[state_code]["total_schedules"] += 1
            else:
                # No county assigned — check if we have any state info at all
                if schedule.populated_place:
                    # Has a place but no county (shouldn't happen, but handle it)
                    schedules_missing_county.append(
                        {
                            "schedule": schedule,
                            "issue": "Populated place set but no county",
                        }
                    )
                    no_state_schedules["missing_county"].append(schedule)
                else:
                    schedules_missing_location.append(
                        {
                            "schedule": schedule,
                            "issue": "No county or populated place assigned",
                        }
                    )
                    no_state_schedules["missing_location"].append(schedule)

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
        total_blank_county = 0
        total_issues = total_missing_location + total_missing_county

        context = {
            "title": "Missing County Analysis",
            "total_schedules": total_schedules,
            "total_with_county": total_with_county,
            "total_missing_location": total_missing_location,
            "total_missing_county": total_missing_county,
            "total_blank_county": total_blank_county,
            "total_issues": total_issues,
            "completion_percentage": (
                round((total_with_county / total_schedules) * 100, 1)
                if total_schedules > 0
                else 0
            ),
            "state_summary": state_summary,
            "schedules_missing_location": schedules_missing_location[
                :50
            ],  # Limit for performance
            "schedules_missing_county": schedules_missing_county[:50],
            "schedules_with_blank_county": [],
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
            "Location & Denomination",
            {
                "fields": [
                    "county",
                    "populated_place",
                    "schedule_denomination",
                ],
                "description": "Primary location and denomination for this schedule.",
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
    autocomplete_fields = ["county", "populated_place", "schedule_denomination"]
    inlines = [
        ReligiousBodyInline,
        MembershipInline,
        ClergyInline,
        ScheduleTranscriptionInline,
    ]

    def get_fieldsets(self, request, obj=None):
        """Restrict Project Management fields for transcribers."""
        fieldsets = super().get_fieldsets(request, obj)
        if is_transcriber_only(request.user):
            return [
                (
                    (name, opts)
                    if name != "Project Management"
                    else (
                        name,
                        {
                            **opts,
                            "fields": ["transcription_status", "transcription_notes"],
                        },
                    )
                )
                for name, opts in fieldsets
            ]
        return fieldsets

    def location_export_view(self, request):
        """View to filter and export census schedules by location"""
        # Get all unique populated places with census schedules
        places = (
            PopulatedPlace.objects.filter(census_schedules__isnull=False)
            .distinct()
            .select_related("county__state")
            .order_by("county__state__code", "county__name", "name")
        )

        # Organize places by state for better display
        places_by_state = defaultdict(list)
        for place in places:
            state = (
                place.county.state.code
                if place.county and place.county.state
                else "Unknown"
            )
            places_by_state[state].append(place)

        # Sort states
        sorted_states = sorted(places_by_state.items())

        if request.method == "POST":
            place_id = request.POST.get("place_id")
            export_format = request.POST.get("export_format", "xlsx")

            if not place_id:
                messages.error(request, "Please select a location.")
                return HttpResponseRedirect(request.path)

            # Get the populated place
            try:
                place = PopulatedPlace.objects.select_related("county__state").get(
                    pk=place_id
                )
            except PopulatedPlace.DoesNotExist:
                messages.error(request, "Location not found.")
                return HttpResponseRedirect(request.path)

            # Get all census schedules for this populated place
            schedules = (
                CensusSchedule.objects.filter(populated_place=place)
                .select_related("county__state", "populated_place")
                .prefetch_related(
                    "church_details__denomination",
                    "membership_details",
                    "clergy",
                )
                .distinct()
            )

            # Export the data
            resource = CensusScheduleResource()
            dataset = resource.export(schedules)

            # Generate filename
            county_name = place.county.name if place.county else "Unknown"
            state_code = (
                place.county.state.code
                if place.county and place.county.state
                else "Unknown"
            )
            location_str = f"{place.name}_{county_name}_{state_code}".replace(" ", "_")
            filename = f"census_schedules_{location_str}"

            # Return appropriate response based on format
            if export_format == "csv":
                response = HttpResponse(dataset.csv, content_type="text/csv")
                response["Content-Disposition"] = (
                    f'attachment; filename="{filename}.csv"'
                )
            elif export_format == "json":
                response = HttpResponse(dataset.json, content_type="application/json")
                response["Content-Disposition"] = (
                    f'attachment; filename="{filename}.json"'
                )
            else:  # xlsx
                response = HttpResponse(
                    dataset.xlsx,
                    content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
                response["Content-Disposition"] = (
                    f'attachment; filename="{filename}.xlsx"'
                )

            return response

        context = {
            **self.admin_site.each_context(request),
            "title": "Export Census Schedules by Location",
            "places_by_state": sorted_states,
            "opts": self.model._meta,
        }

        return render(request, "admin/census/location_export.html", context)

    def transcription_status_display(self, obj):
        """Display status with consistent admin badge styling."""
        status_class = obj.transcription_status.replace("_", "-")
        return format_html(
            '<span class="status-badge status-{}">{}</span>',
            status_class,
            obj.get_transcription_status_display(),
        )

    transcription_status_display.short_description = "Status"

    @admin.display(description="County")
    def get_location_display(self, obj):
        """Display location from county/state hierarchy"""
        if obj.populated_place:
            return str(obj.populated_place)
        elif obj.county:
            return str(obj.county)
        return "-"

    def get_queryset(self, request):
        """Filter records based on user permissions and optimize queries"""
        qs = super().get_queryset(request)

        # Optimize foreign key lookups (including new location hierarchy)
        qs = qs.select_related(
            "assigned_transcriber",
            "assigned_reviewer",
            "county",
            "county__state",
            "populated_place",
            "populated_place__county",
            "schedule_denomination",
        )

        # Prefetch related inlines to reduce queries
        qs = qs.prefetch_related(
            "church_details",
            "church_details__denomination",
            "membership_details",
            "membership_details__religious_body",
            "clergy",
        )

        # If user is ONLY in Transcribers group (student transcriber), only show their assigned records
        # Superusers and users in multiple groups (like admins) see all records
        if is_transcriber_only(request.user):
            return qs.filter(assigned_transcriber=request.user)

        return qs

    def has_delete_permission(self, request, obj=None):
        """Hide delete button on change form; only superusers can delete."""
        if obj is not None and not request.user.is_superuser:
            return False
        if request.user.groups.filter(name="Transcribers").exists():
            return False
        return super().has_delete_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        if (
            obj is not None
            and is_transcriber_only(request.user)
            and obj.transcription_status in LOCKED_FOR_TRANSCRIBERS
        ):
            return False
        return super().has_change_permission(request, obj)

    def save_model(self, request, obj, form, change):
        """Auto-set status when students save their work"""
        if (
            is_transcriber_only(request.user)
            and change
            and obj.transcription_status == "assigned"
        ):
            obj.transcription_status = "in_progress"

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
        "get_schedule_location",
        "num_edifices",
        "edifice_value",
    ]
    list_filter = [
        "denomination",
        "census_record__county__state",
    ]
    search_fields = [
        "name",
        "address",
        "denomination__name",
        "denomination__short_name",
        "census_record__schedule_title",
        "census_record__schedule_id",
        "census_record__county__name",
        "census_record__county__state__name",
        "census_record__county__state__code",
        "census_record__populated_place__name",
    ]
    autocomplete_fields = ["denomination", "census_record"]

    readonly_fields = [
        "geocode_status",
        "geocoded_at",
        "created_at",
        "updated_at",
    ]

    @admin.display(description="Location")
    def get_schedule_location(self, obj):
        """Display location from the parent CensusSchedule"""
        if obj.census_record:
            if obj.census_record.populated_place:
                return str(obj.census_record.populated_place)
            elif obj.census_record.county:
                return str(obj.census_record.county)
        return "-"

    def get_queryset(self, request):
        """Optimize queries for list display"""
        qs = super().get_queryset(request)
        return qs.select_related(
            "denomination",
            "census_record",
            "census_record__county",
            "census_record__county__state",
            "census_record__populated_place",
        )

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
            "Street Address",
            {
                "fields": [
                    "address",
                    "urban_rural_code",
                ],
                "description": "Street-level address for this specific church. County/city location is set on the Census Schedule.",
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

    def geocode_status_display(self, obj):
        """Display geocoding status with color coding."""
        if obj.geocode_status == "success":
            return "✓ Geocoded"
        elif obj.geocode_status == "failed":
            return "✗ Failed"
        elif obj.geocode_status == "pending":
            return "Pending"
        elif obj.geocode_status == "skipped":
            return "− Skipped"
        return "− Not Attempted"

    geocode_status_display.short_description = "Geocode Status"

    history_list_display = ["changed_fields"]
