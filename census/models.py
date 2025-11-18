import logging

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords

from location.models import Location

logger = logging.getLogger(__name__)


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

    # Record keeping
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    def __str__(self):
        return self.name


class CensusSchedule(models.Model):
    """
    This model serves as the primary record that ties together all related data
    for a specific schedule.
    """

    TRANSCRIPTION_STATUS_CHOICES = [
        ("unassigned", "Unassigned"),
        ("assigned", "Assigned"),
        ("in_progress", "In Progress"),
        ("needs_review", "Needs Review"),
        ("completed", "Transcribed"),
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
            # Composite index for common filter combinations
            models.Index(
                fields=["transcription_status", "assigned_transcriber"],
                name="census_status_transcriber_idx",
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
    location = models.ForeignKey(
        Location,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        help_text="Use the magnifying glass to the right to search for a location. Do not manually edit this number.",
    )
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

    def save(self, *args, **kwargs):
        """
        Override save to automatically geocode address on save.
        """
        # Check if geocoding should be performed
        from census.geocoding import GeocodingError, geocode_address, should_geocode

        if should_geocode(self):
            logger.info(f"Attempting to geocode ReligiousBody: {self.name}")

            # Extract location context from related Location
            city = None
            county = None
            state = None

            if self.location:
                city = self.location.city
                county = self.location.county
                state = self.location.state

            try:
                # Perform geocoding
                lat, lon, status = geocode_address(
                    address=self.address, city=city, county=county, state=state
                )

                # Update geocoding fields
                self.latitude = lat
                self.longitude = lon
                self.geocode_status = status
                self.geocoded_at = timezone.now()

                if status == "success":
                    logger.info(
                        f"Successfully geocoded {self.name} to ({lat:.6f}, {lon:.6f})"
                    )
                elif status == "failed":
                    logger.warning(f"Geocoding failed for {self.name}")

            except GeocodingError as e:
                logger.error(f"Geocoding error for {self.name}: {e}")
                self.geocode_status = "failed"
                self.geocoded_at = timezone.now()

        # Call parent save
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Religious Body"
        verbose_name_plural = "Religious Body"

        indexes = [
            models.Index(fields=["denomination"]),
            models.Index(fields=["location"]),
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
