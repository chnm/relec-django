from django.db import models
from simple_history.models import HistoricalRecords

from location.models import Location


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

    resource_id = models.IntegerField(unique=True, verbose_name="Record ID")
    schedule_title = models.CharField(max_length=255)
    schedule_id = models.CharField(max_length=50, verbose_name="Schedule ID")
    box = models.CharField(max_length=255, blank=True, null=True)
    notes = models.TextField(null=True, blank=True)

    # Reference fields from original system
    datascribe_omeka_item_id = models.IntegerField(
        verbose_name="DataScribe Omeka Item ID",
        help_text="This record is read-only and not editable.",
    )
    datascribe_item_id = models.IntegerField(
        verbose_name="DataScribe Item ID",
        help_text="This record is read-only and not editable.",
    )
    datascribe_record_id = models.IntegerField(
        verbose_name="DataScribe Record ID",
        help_text="This record is read-only and not editable.",
    )
    datascribe_original_image_path = models.CharField(
        max_length=255,
        verbose_name="DataScribe Original Image Path",
    )
    omeka_storage_id = models.CharField(
        max_length=255,
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
        ]

    def __str__(self):
        return f"Census Record {self.resource_id}"


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

    class Meta:
        verbose_name = "Religious Body"
        verbose_name_plural = "Religious Body"

        indexes = [
            models.Index(fields=["denomination"]),
            models.Index(fields=["location"]),
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

    class Meta:
        verbose_name = "Membership"
        verbose_name_plural = "Membership"

    # Record keeping
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()


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
