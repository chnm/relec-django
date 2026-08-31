import logging
import uuid

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from simple_history.models import HistoricalRecords

from location.models import County, PopulatedPlace

logger = logging.getLogger(__name__)


class ImmutableQuerySet(models.QuerySet):
    """Block bulk writes that would bypass a model's immutability checks."""

    def update(self, **kwargs):
        raise ValidationError("Immutable records cannot be updated in bulk.")

    def delete(self):
        raise ValidationError("Immutable records cannot be deleted.")

    def bulk_update(self, objs, fields, batch_size=None):
        raise ValidationError("Immutable records cannot be updated in bulk.")


class ProtectedTranscriptionJobQuerySet(models.QuerySet):
    """Keep raw provider evidence immutable while allowing workflow updates."""

    IMMUTABLE_FIELDS = {
        "raw_result",
        "usage",
        "provider_message_id",
        "stop_reason",
        "input_tokens",
        "output_tokens",
        "cache_creation_input_tokens",
        "cache_read_input_tokens",
    }

    def update(self, **kwargs):
        protected = self.IMMUTABLE_FIELDS.intersection(kwargs)
        if protected:
            fields = ", ".join(sorted(protected))
            raise ValidationError(f"Immutable job fields cannot be updated: {fields}.")
        return super().update(**kwargs)


def to_numeric(value, default=0):
    """
    Attempts to convert a value to a number.
    Returns default if the value is None.
    For use in data processing and calculations.
    """
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def is_boolean_true(value):
    """
    Checks if a value represents a boolean true.
    Returns True if the value is "Yes" or True, False otherwise.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() == "yes"
    return False


class Denomination(models.Model):
    """
    This model represents a religious denomination.
    """

    id = models.AutoField(primary_key=True)
    denomination_id = models.CharField(max_length=50, unique=True, null=True)
    name = models.CharField(max_length=255)
    short_name = models.CharField(max_length=255, null=True)
    family_census = models.CharField(null=True, max_length=255)
    family_relec = models.CharField(null=True, max_length=255)

    # Published census counts (from 1926 Census of Religious Bodies, Vol. 1)
    published_churches_count = models.IntegerField(
        null=True,
        blank=True,
        verbose_name="Published Churches Count",
        help_text="Number of churches reported in the published 1926 census volume",
    )

    # Record keeping
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    def __str__(self):
        return self.name


class DenominationCensusReport(models.Model):
    """
    PDF census report associated with a denomination, imported from Omeka.
    """

    denomination = models.ForeignKey(
        Denomination,
        on_delete=models.CASCADE,
        related_name="census_reports",
    )
    pdf_file = models.FileField(
        upload_to="denomination_reports/",
        verbose_name="Census Report PDF",
    )
    title = models.CharField(max_length=255, blank=True)
    original_filename = models.CharField(max_length=255, blank=True)

    # Omeka tracking
    omeka_item_id = models.IntegerField(null=True, blank=True)
    omeka_media_id = models.IntegerField(null=True, blank=True, unique=True)

    # Record keeping
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    def __str__(self):
        return self.title or self.original_filename

    class Meta:
        verbose_name = "Denomination Census Report"
        verbose_name_plural = "Denomination Census Reports"


class CensusSchedule(models.Model):
    """
    This model serves as the primary record that ties together all related data
    for a specific schedule.
    """

    TRANSCRIPTION_STATUS_CHOICES = [
        ("unassigned", "Unassigned"),
        ("assigned", "Assigned"),
        ("in_progress", "In Progress"),
        ("needs_review", "Imported - Needs Review"),
        ("completed", "Ready for Review"),
        ("approved", "Approved"),
    ]

    resource_id = models.IntegerField(unique=True, verbose_name="Record ID")
    schedule_title = models.CharField(max_length=255)
    schedule_id = models.CharField(max_length=50, verbose_name="Schedule ID")
    box = models.CharField(max_length=255, blank=True, null=True)
    notes = models.TextField(null=True, blank=True)

    # Project management fields
    transcription_status = models.CharField(
        max_length=20,
        choices=TRANSCRIPTION_STATUS_CHOICES,
        default="unassigned",
        verbose_name="Transcription Status",
    )
    assigned_transcriber = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_transcriptions",
        verbose_name="Assigned Transcriber",
    )
    assigned_reviewer = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_reviews",
        verbose_name="Assigned Reviewer",
    )
    transcription_notes = models.TextField(
        blank=True,
        null=True,
        verbose_name="Transcription Notes",
        help_text="Notes about the transcription process or issues",
    )

    # Reference fields from original system
    datascribe_omeka_item_id = models.IntegerField(
        null=True,
        blank=True,
        verbose_name="DataScribe Omeka Item ID",
        help_text="This record is read-only and not editable.",
    )
    datascribe_item_id = models.IntegerField(
        null=True,
        blank=True,
        verbose_name="DataScribe Item ID",
        help_text="This record is read-only and not editable.",
    )
    datascribe_record_id = models.IntegerField(
        null=True,
        blank=True,
        verbose_name="DataScribe Record ID",
        help_text="This record is read-only and not editable.",
    )
    datascribe_original_image_path = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="DataScribe Original Image Path",
    )
    omeka_storage_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Omeka Storage ID",
    )

    # Image fields
    original_image = models.ImageField(
        upload_to="census_images/originals/",
        blank=True,
        null=True,
        verbose_name="Original Census Schedule Image",
        help_text="High-resolution image of the original census schedule",
    )

    # Location fields
    county = models.ForeignKey(
        County,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="census_schedules",
        verbose_name="County",
        help_text="The county where this census was taken",
    )
    populated_place = models.ForeignKey(
        PopulatedPlace,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="census_schedules",
        verbose_name="Populated Place",
        help_text="The specific city/town where this census was taken as city, county, state (optional)",
    )

    # Denomination (moved from ReligiousBody for schedule-level assignment)
    schedule_denomination = models.ForeignKey(
        "Denomination",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="census_schedules",
        verbose_name="Denomination",
        help_text="The denomination associated with this census schedule",
    )

    # Legacy transcription storage retained temporarily as rollback evidence while
    # the run-based model is validated. New code must use ScheduleTranscription.
    ai_transcription = models.JSONField(
        null=True,
        blank=True,
        verbose_name="AI transcription",
        help_text="Raw JSON response from agentic transcription of the census schedule image",
    )
    human_transcription = models.JSONField(
        null=True,
        blank=True,
        verbose_name="Original human transcription",
        help_text="The raw JSON response from the human transcribers of the census schedule image, available for comparison against AI transcriptions.",
    )

    # Pastor count (form field 26)
    num_assistant_pastors = models.IntegerField(
        null=True,
        blank=True,
        verbose_name="Number of assistant pastors",
        help_text="Number of ordained ministers employed as assistant pastors (field 26)",
    )

    # Respondent (person who signed the bottom of the form)
    respondent_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Signature of person furnishing information",
    )
    respondent_title = models.CharField(
        max_length=255,
        blank=True,
        help_text="Official title of person furnishing information (e.g., Pastor, Clerk)",
    )
    respondent_po_address = models.CharField(
        max_length=255,
        blank=True,
        help_text="P.O. address of person furnishing information",
    )
    respondent_date_signed = models.CharField(
        max_length=10,
        blank=True,
        help_text="Date signed (YYYY-MM-DD or YYYY if partial)",
    )

    # Census Bureau processing metadata
    date_received = models.DateField(
        null=True,
        blank=True,
        help_text="Date the Census Bureau received this schedule (from receipt stamp)",
    )
    district_stamp = models.CharField(
        max_length=100,
        blank=True,
        help_text="Census Bureau district stamp (e.g., 'Denver, D')",
    )
    denomination_code_stamp = models.CharField(
        max_length=20,
        blank=True,
        help_text="Full denomination code stamp in cursive (e.g., '0-1-3')",
    )

    # Marginalia and transcriber notes
    marginalia = models.JSONField(
        default=list,
        blank=True,
        help_text="Array of {page_location, marginalia_transcription} for handwritten marks not captured elsewhere",
    )
    ai_notes = models.TextField(
        blank=True,
        help_text="Free-form observations from the AI transcriber about anomalies, illegibility, or decisions",
    )
    # Record keeping
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords(excluded_fields=["original_image"])

    class Meta:
        indexes = [
            models.Index(fields=["schedule_id"]),
            models.Index(fields=["datascribe_omeka_item_id"]),
            models.Index(fields=["transcription_status"]),
            models.Index(fields=["assigned_transcriber"]),
            models.Index(fields=["assigned_reviewer"]),
            models.Index(fields=["county"]),
            models.Index(fields=["populated_place"]),
            models.Index(fields=["schedule_denomination"]),
            # Composite index for common filter combinations
            models.Index(
                fields=["transcription_status", "assigned_transcriber"],
                name="census_status_transcriber_idx",
            ),
            # Location-based query index
            models.Index(
                fields=["county", "schedule_denomination"],
                name="census_county_denom_idx",
            ),
        ]

    def save(self, *args, **kwargs):
        # Auto-transition status based on assignments
        if self.assigned_transcriber and self.transcription_status == "unassigned":
            self.transcription_status = "assigned"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Census Record {self.resource_id}"

    def get_status_display_color(self):
        """Return CSS class for status display"""
        status_colors = {
            "unassigned": "gray",
            "assigned": "blue",
            "in_progress": "orange",
            "needs_review": "yellow",
            "completed": "green",
            "approved": "dark-green",
        }
        return status_colors.get(self.transcription_status, "gray")


class TranscriptionRun(models.Model):
    """A named batch of human or agentic transcription work."""

    KIND_CHOICES = [
        ("human_snapshot", "Human snapshot"),
        ("agent", "Agent"),
    ]

    key = models.SlugField(
        max_length=120,
        unique=True,
        help_text="Stable identifier for this run, such as walter-gemini-2026-08-26.",
    )
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Optional run-level provenance such as model, prompt, or code versions.",
    )
    objects = ImmutableQuerySet.as_manager()
    created_at = models.DateTimeField(auto_now_add=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ["-created_at", "key"]

    def __str__(self):
        return self.key

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError(
                "Transcription run provenance is immutable; create a new run instead."
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Transcription runs are immutable.")

    @property
    def token_usage(self):
        """Aggregate provider-reported token usage across this run's jobs."""
        usage = self.transcription_jobs.aggregate(
            input_tokens=models.Sum("input_tokens"),
            output_tokens=models.Sum("output_tokens"),
            cache_creation_input_tokens=models.Sum("cache_creation_input_tokens"),
            cache_read_input_tokens=models.Sum("cache_read_input_tokens"),
        )
        usage["total_input_tokens"] = sum(
            usage[field] or 0
            for field in (
                "input_tokens",
                "cache_creation_input_tokens",
                "cache_read_input_tokens",
            )
        )
        return usage


class ScheduleTranscription(models.Model):
    """Immutable transcription output for one schedule in one run."""

    census_schedule = models.ForeignKey(
        CensusSchedule,
        on_delete=models.PROTECT,
        related_name="transcriptions",
    )
    run = models.ForeignKey(
        TranscriptionRun,
        on_delete=models.PROTECT,
        related_name="schedule_transcriptions",
    )
    data = models.JSONField(
        help_text="Raw transcription JSON. Agent notes belong inside this object.",
    )
    objects = ImmutableQuerySet.as_manager()
    created_at = models.DateTimeField(auto_now_add=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ["created_at", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["census_schedule", "run"],
                name="unique_schedule_transcription_run",
            )
        ]

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError(
                "Schedule transcription outputs are immutable; create a new run instead."
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Schedule transcription outputs are immutable.")

    def __str__(self):
        return f"{self.census_schedule} / {self.run.key}"


class ScheduleReconciliation(models.Model):
    """Append-only evidence for one reviewer approval decision."""

    class Outcome(models.TextChoices):
        RETAINED_CURRENT = "retained_current", "Kept canonical data"
        PROMOTED_CANDIDATE = (
            "promoted_candidate",
            "Promoted one evidence source",
        )
        MIXED = "mixed", "Combined evidence and reviewer edits"
        ROLLED_BACK = "rolled_back", "Restored previous canonical data"

    census_schedule = models.ForeignKey(
        CensusSchedule,
        on_delete=models.PROTECT,
        related_name="reconciliations",
    )
    reviewer = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="schedule_reconciliations",
    )
    outcome = models.CharField(max_length=30, choices=Outcome.choices)
    notes = models.TextField(blank=True)
    canonical_before = models.JSONField()
    canonical_after = models.JSONField()
    before_fingerprint = models.CharField(max_length=64)
    after_fingerprint = models.CharField(max_length=64)
    decisions = models.JSONField(default=dict)
    reverses = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="reversals",
    )
    applied_at = models.DateTimeField(auto_now_add=True)
    objects = ImmutableQuerySet.as_manager()

    class Meta:
        ordering = ["-applied_at", "-pk"]

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError(
                "Schedule reconciliation evidence is immutable; create a new event."
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Schedule reconciliation evidence is immutable.")

    def __str__(self):
        return f"{self.census_schedule} / {self.get_outcome_display()}"


class ReconciliationSource(models.Model):
    """Final disposition of immutable evidence in a reconciliation."""

    class Disposition(models.TextChoices):
        ACCEPTED = "accepted", "Accepted"
        INCORPORATED = "incorporated", "Partially incorporated"
        REJECTED = "rejected", "Rejected"
        SUPERSEDED = "superseded", "Superseded"

    reconciliation = models.ForeignKey(
        ScheduleReconciliation,
        on_delete=models.PROTECT,
        related_name="sources",
    )
    transcription = models.ForeignKey(
        ScheduleTranscription,
        on_delete=models.PROTECT,
        related_name="reconciliation_sources",
    )
    disposition = models.CharField(max_length=20, choices=Disposition.choices)
    objects = ImmutableQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["reconciliation", "transcription"],
                name="unique_reconciliation_transcription_source",
            )
        ]

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError(
                "Reconciliation source dispositions are immutable."
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Reconciliation source dispositions are immutable.")

    def __str__(self):
        return f"{self.transcription} / {self.get_disposition_display()}"


class TranscriptionBatch(models.Model):
    """A durable submission to a provider's asynchronous batch API."""

    class State(models.TextChoices):
        QUEUED = "queued", "Queued"
        SUBMITTING = "submitting", "Submitting"
        IN_PROGRESS = "in_progress", "In progress"
        COLLECTING = "collecting", "Collecting"
        ENDED = "ended", "Ended"
        FAILED = "failed", "Failed"
        CANCELED = "canceled", "Canceled"
        NEEDS_RECOVERY = "needs_recovery", "Needs manual recovery"

    #: States in which a batch is still the worker's responsibility.
    ACTIVE_STATES = (
        State.QUEUED,
        State.SUBMITTING,
        State.IN_PROGRESS,
        State.COLLECTING,
    )

    run = models.ForeignKey(
        TranscriptionRun,
        on_delete=models.PROTECT,
        related_name="transcription_batches",
    )
    provider = models.CharField(max_length=30, default="anthropic")
    state = models.CharField(
        max_length=30,
        choices=State.choices,
        default=State.QUEUED,
        db_index=True,
    )
    provider_batch_id = models.CharField(
        max_length=120,
        null=True,
        blank=True,
        unique=True,
    )
    request_count = models.PositiveIntegerField(default=0)
    encoded_size_bytes = models.PositiveBigIntegerField(default=0)
    request_counts = models.JSONField(default=dict, blank=True)
    provider_snapshot = models.JSONField(null=True, blank=True)
    error = models.JSONField(null=True, blank=True)
    lease_token = models.UUIDField(null=True, blank=True)
    lease_expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    heartbeat_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    provider_expires_at = models.DateTimeField(null=True, blank=True)
    provider_ended_at = models.DateTimeField(null=True, blank=True)
    collected_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ["created_at", "pk"]
        indexes = [
            models.Index(fields=["state", "lease_expires_at"]),
            models.Index(fields=["run", "state"]),
        ]

    def __str__(self):
        return self.provider_batch_id or f"Local batch {self.pk or 'unsaved'}"


def transcription_job_custom_id():
    return f"job_{uuid.uuid4().hex}"


class TranscriptionJob(models.Model):
    """One schedule attempt and its immutable raw provider result."""

    class State(models.TextChoices):
        QUEUED = "queued", "Queued"
        PREPARING = "preparing", "Preparing"
        SUBMITTED = "submitted", "Submitted"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        EXPIRED = "expired", "Expired"
        CANCELED = "canceled", "Canceled"
        INVALID = "invalid", "Invalid response"
        NEEDS_RECOVERY = "needs_recovery", "Needs manual recovery"

    census_schedule = models.ForeignKey(
        CensusSchedule,
        on_delete=models.PROTECT,
        related_name="transcription_jobs",
    )
    run = models.ForeignKey(
        TranscriptionRun,
        on_delete=models.PROTECT,
        related_name="transcription_jobs",
    )
    batch = models.ForeignKey(
        TranscriptionBatch,
        on_delete=models.PROTECT,
        related_name="jobs",
        null=True,
        blank=True,
    )
    custom_id = models.CharField(
        max_length=64,
        unique=True,
        default=transcription_job_custom_id,
        editable=False,
    )
    attempt = models.PositiveIntegerField(default=1)
    state = models.CharField(
        max_length=30,
        choices=State.choices,
        default=State.QUEUED,
        db_index=True,
    )
    raw_result = models.JSONField(null=True, blank=True)
    provider_message_id = models.CharField(max_length=120, null=True, blank=True)
    stop_reason = models.CharField(max_length=60, null=True, blank=True)
    usage = models.JSONField(null=True, blank=True)
    input_tokens = models.PositiveIntegerField(null=True, blank=True)
    output_tokens = models.PositiveIntegerField(null=True, blank=True)
    cache_creation_input_tokens = models.PositiveIntegerField(null=True, blank=True)
    cache_read_input_tokens = models.PositiveIntegerField(null=True, blank=True)
    error_type = models.CharField(max_length=100, blank=True)
    error_message = models.TextField(blank=True)
    queued_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    objects = ProtectedTranscriptionJobQuerySet.as_manager()
    history = HistoricalRecords()

    class Meta:
        ordering = ["queued_at", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["census_schedule", "run", "attempt"],
                name="unique_schedule_run_attempt",
            ),
            models.UniqueConstraint(
                fields=["census_schedule", "run"],
                condition=models.Q(
                    state__in=[
                        "queued",
                        "preparing",
                        "submitted",
                        "succeeded",
                        "needs_recovery",
                    ]
                ),
                name="unique_active_schedule_run_job",
            ),
        ]
        indexes = [
            models.Index(fields=["state", "queued_at"]),
            models.Index(fields=["run", "state"]),
        ]

    def clean(self):
        super().clean()
        if self.batch_id and self.run_id and self.batch.run_id != self.run_id:
            raise ValidationError({"batch": "The batch must belong to the same run."})

    def save(self, *args, **kwargs):
        if self.pk:
            evidence_fields = tuple(ProtectedTranscriptionJobQuerySet.IMMUTABLE_FIELDS)
            original = (
                type(self).objects.filter(pk=self.pk).values(*evidence_fields).first()
            )
            if original:
                evidence_recorded = original["raw_result"] is not None
                for field in evidence_fields:
                    previous = original[field]
                    current = getattr(self, field)
                    if evidence_recorded and current != previous:
                        raise ValidationError(
                            f"A transcription job's provider evidence is immutable "
                            f"once recorded ({field})."
                        )
        self.full_clean(exclude=None)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.custom_id}: {self.census_schedule}"

    @property
    def total_input_tokens(self):
        return sum(
            value or 0
            for value in (
                self.input_tokens,
                self.cache_creation_input_tokens,
                self.cache_read_input_tokens,
            )
        )


class ReligiousBody(models.Model):
    census_record = models.ForeignKey(
        "census.CensusSchedule",
        on_delete=models.CASCADE,
        related_name="church_details",
    )
    denomination = models.ForeignKey(
        Denomination,
        on_delete=models.PROTECT,
        help_text="Select the denomination associated with this religious body.",
        null=True,
    )
    name = models.CharField(
        max_length=255,
        verbose_name="Local church name",
        help_text="The name of the church as it appears in the census record.",
        blank=True,
        null=True,
    )
    census_code = models.CharField(null=True, blank=True, max_length=50)
    division = models.CharField(null=True, blank=True, max_length=100)

    # Location fields
    address = models.CharField(max_length=255, null=True, blank=True)
    urban_rural_code = models.CharField(
        blank=True, null=True, max_length=50, verbose_name="Urban/rural code"
    )

    # Geocoding fields for specific address
    latitude = models.FloatField(
        blank=True,
        null=True,
        verbose_name="Latitude",
        help_text="Automatically geocoded from address. Leave blank to auto-geocode on save.",
    )
    longitude = models.FloatField(
        blank=True,
        null=True,
        verbose_name="Longitude",
        help_text="Automatically geocoded from address. Leave blank to auto-geocode on save.",
    )
    geocode_status = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        choices=[
            ("pending", "Pending Geocoding"),
            ("success", "Successfully Geocoded"),
            ("failed", "Geocoding Failed"),
            ("skipped", "Skipped (No Address)"),
        ],
        verbose_name="Geocode Status",
        help_text="Status of automatic geocoding process.",
    )
    geocoded_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name="Geocoded At",
        help_text="Timestamp when geocoding was last attempted.",
    )

    # Church property details
    num_edifices = models.IntegerField(
        blank=True,
        null=True,
        verbose_name="Number of edifices",
        help_text="Leave blank if information is missing or illegible",
    )
    edifice_value = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        blank=True,
        null=True,
        verbose_name="Value of church edifices",
        help_text="Leave blank if information is missing or illegible",
    )
    edifice_debt = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        blank=True,
        null=True,
        verbose_name="Debt on church edifices",
        help_text="Leave blank if information is missing or illegible",
    )

    # Parsonage details
    has_pastors_residence = models.BooleanField(
        null=True,
        blank=True,
        verbose_name="Ownership of pastor's residence",
        help_text="Set to Unknown if missing, illegible, or unknown.",
    )
    residence_value = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        blank=True,
        null=True,
        verbose_name="Value of pastor's residence",
        help_text="Leave blank if information is missing or illegible",
    )
    residence_debt = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        blank=True,
        null=True,
        verbose_name="Debt on pastor's residence",
        help_text="Leave blank if information is missing or illegible",
    )

    # Finances
    expenses = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        blank=True,
        null=True,
        verbose_name="Expenses",
        help_text="Leave blank if information is missing or illegible",
    )
    benevolences = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        blank=True,
        null=True,
        verbose_name="Benevolences",
        help_text="Leave blank if information is missing or illegible",
    )
    total_expenditures = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        blank=True,
        null=True,
        verbose_name="Total annual expenditures",
        help_text="Leave blank if information is missing or illegible",
    )

    # Record keeping
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    def __str__(self):
        # if name return name, otherwise "no name provided"
        return self.name if self.name is not None else "No name provided"

    # def save(self, *args, **kwargs):
    #    super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Religious Body"
        verbose_name_plural = "Religious Body"

        indexes = [
            models.Index(fields=["denomination"]),
            models.Index(fields=["census_record"]),
            # Composite index for common queries
            models.Index(
                fields=["census_record", "denomination"],
                name="census_rb_census_denom_idx",
            ),
        ]


class Membership(models.Model):
    census_record = models.ForeignKey(
        "census.CensusSchedule",
        on_delete=models.CASCADE,
        related_name="membership_details",
    )
    religious_body = models.ForeignKey(
        "ReligiousBody", on_delete=models.CASCADE, related_name="membership", null=True
    )
    male_members = models.IntegerField(
        blank=True,
        null=True,
        verbose_name="Male Members",
        help_text="Leave blank if information is missing or illegible",
    )
    female_members = models.IntegerField(
        blank=True,
        null=True,
        verbose_name="Female Members",
        help_text="Leave blank if information is missing or illegible",
    )
    total_members_by_sex = models.IntegerField(
        blank=True,
        null=True,
        verbose_name="Total Members by Sex",
        help_text="Leave blank if information is missing or illegible",
    )
    members_under_13 = models.IntegerField(
        blank=True,
        null=True,
        verbose_name="Members Under 13",
        help_text="Leave blank if information is missing or illegible",
    )
    members_13_and_older = models.IntegerField(
        blank=True,
        null=True,
        verbose_name="Members 13 and Older",
        help_text="Leave blank if information is missing or illegible",
    )
    total_members_by_age = models.IntegerField(
        blank=True,
        null=True,
        verbose_name="Total Members by Age",
        help_text="Leave blank if information is missing or illegible",
    )

    # Sunday school
    sunday_school_num_officers_teachers = models.IntegerField(
        blank=True,
        null=True,
        verbose_name="Sunday Schools - Number of Officers/Teachers",
        help_text="Leave blank if information is missing or illegible",
    )
    sunday_school_num_scholars = models.IntegerField(
        blank=True,
        null=True,
        verbose_name="Sunday Schools - Number of Scholars",
        help_text="Leave blank if information is missing or illegible",
    )

    # Vacation Bible school
    vbs_num_officers_teachers = models.IntegerField(
        blank=True,
        null=True,
        verbose_name="Vacation Bible Schools - Number of Officers/Teachers",
        help_text="Leave blank if information is missing or illegible",
    )
    vbs_num_scholars = models.IntegerField(
        blank=True,
        null=True,
        verbose_name="Vacation Bible Schools - Number of Scholars",
        help_text="Leave blank if information is missing or illegible",
    )

    # Weekday religious school fields
    weekday_num_officers_teachers = models.IntegerField(
        blank=True,
        null=True,
        verbose_name="Week-day Religious Schools - Number of Officers/Teachers",
        help_text="Leave blank if information is missing or illegible",
    )
    weekday_num_scholars = models.IntegerField(
        blank=True,
        null=True,
        verbose_name="Week-day Religious Schools - Number of Scholars",
        help_text="Leave blank if information is missing or illegible",
    )

    # Parochial school
    parochial_num_administrators = models.IntegerField(
        blank=True,
        null=True,
        verbose_name="Parochial Schools - Number of Administrators",
        help_text="Leave blank if information is missing or illegible",
    )
    parochial_num_elementary_teachers = models.IntegerField(
        blank=True,
        null=True,
        verbose_name="Parochial Schools - Number of Elementary Teachers",
        help_text="Leave blank if information is missing or illegible",
    )
    parochial_num_secondary_teachers = models.IntegerField(
        blank=True,
        null=True,
        verbose_name="Parochial Schools - Number of Secondary Teachers",
        help_text="Leave blank if information is missing or illegible",
    )
    parochial_num_elementary_scholars = models.IntegerField(
        blank=True,
        null=True,
        verbose_name="Parochial Schools - Number of Elementary Scholars",
        help_text="Leave blank if information is missing or illegible",
    )
    parochial_num_secondary_scholars = models.IntegerField(
        blank=True,
        null=True,
        verbose_name="Parochial Schools - Number of Secondary Scholars",
        help_text="Leave blank if information is missing or illegible",
    )

    def __str__(self):
        return str(self.religious_body)

    # Record keeping
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    class Meta:
        verbose_name = "Membership"
        verbose_name_plural = "Membership"

        indexes = [
            models.Index(fields=["census_record"]),
            models.Index(fields=["religious_body"]),
            # Composite index for common queries
            models.Index(
                fields=["census_record", "religious_body"],
                name="census_mem_census_rb_idx",
            ),
        ]


class Clergy(models.Model):
    census_schedule = models.ForeignKey(
        "census.CensusSchedule",
        on_delete=models.CASCADE,
        related_name="clergy",
        default=None,
    )
    name = models.CharField(
        max_length=255,
        help_text="The name of the clergy person. Leave blank if information is missing or illegible.",
    )
    is_assistant = models.BooleanField(default=False)
    college = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="The college attended by the clergy person. Leave blank if information is missing or illegible.",
    )
    theological_seminary = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="The theological seminary attended by the clergy person. Leave blank if information is missing or illegible.",
    )
    num_other_churches_served = models.IntegerField(
        blank=True,
        null=True,
        verbose_name="Number of other churches served",
        help_text="Leave blank if information is missing or illegible",
    )
    serving_congregation = models.BooleanField(
        blank=True,
        null=True,
        verbose_name="Pastor serving congregation",
        help_text="Whether the pastor is serving the congregation. Leave blank if information is missing or illegible.",
    )

    # Record keeping
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "Clergy"

        indexes = [
            models.Index(fields=["census_schedule"]),
            models.Index(fields=["is_assistant"]),
        ]
