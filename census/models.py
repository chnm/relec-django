from django.db import models
from simple_history.models import HistoricalRecords

from location.models import Location


class Denomination(models.Model):
    """
    This model represents a religious denomination.
    """

    id = models.AutoField(primary_key=True)
    denomination_id = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=255)
    family_census = models.CharField(max_length=255)
    family_arda = models.CharField(max_length=255)

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

    # Record keeping
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

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
        help_text="Selec the denomination associated with this religious body.",
        null=True,
    )
    name = models.CharField(
        max_length=255,
        verbose_name="Local church name",
        help_text="The name of the church as it appears in the census record.",
        blank=True,
        null=True,
    )
    census_code = models.CharField(max_length=50)
    division = models.CharField(max_length=100)

    # Location fields
    address = models.CharField(max_length=255, null=True, blank=True)
    location = models.ForeignKey(
        Location,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        help_text="Use the magnifying class to the right to search for a location. Do not manually edit this number.",
    )
    urban_rural_code = models.CharField(
        blank=True, null=True, max_length=50, verbose_name="Urban/rural code"
    )

    # Church property details
    num_edifices = models.PositiveIntegerField(
        default=0, blank=True, null=True, verbose_name="Number of edifices"
    )
    edifice_value = models.DecimalField(
        max_digits=12, decimal_places=2, blank=True, null=True
    )
    edifice_debt = models.DecimalField(
        max_digits=12, decimal_places=2, blank=True, null=True
    )

    # Parsonage details
    has_pastors_residence = models.BooleanField(default=False)
    residence_value = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    residence_debt = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )

    # Finances
    expenses = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, null=True, blank=True
    )
    benevolences = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, blank=True
    )
    total_expenditures = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, blank=True
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
    male_members = models.PositiveIntegerField(default=0, verbose_name="Male Members")
    female_members = models.PositiveIntegerField(
        default=0, verbose_name="Female Members", null=True
    )
    members_under_13 = models.PositiveIntegerField(
        default=0, verbose_name="Members Under 13", null=True
    )
    members_13_and_older = models.PositiveIntegerField(
        default=0, verbose_name="Members 13 and Older", null=True
    )

    # Sunday school
    sunday_school_num_officers_teachers = models.PositiveIntegerField(
        default=0, verbose_name="Number of Officers/Teachers", null=True
    )
    sunday_school_num_scholars = models.PositiveIntegerField(
        default=0, verbose_name="Number of Scholars", null=True
    )

    # Vacation Bible school
    vbs_num_officers_teachers = models.PositiveIntegerField(
        null=True, default=0, verbose_name="Number of Officers/Teachers"
    )
    vbs_num_scholars = models.PositiveIntegerField(
        null=True, default=0, verbose_name="Number of Scholars"
    )

    # Parochial school
    parochial_num_administrators = models.PositiveIntegerField(
        null=True, default=0, verbose_name="Number of Administrators"
    )
    parochial_num_elementary_teachers = models.PositiveIntegerField(
        null=True, default=0, verbose_name="Number of Elementary Teachers"
    )
    parochial_num_secondary_teachers = models.PositiveIntegerField(
        null=True, default=0, verbose_name="Number of Secondary Teachers"
    )
    parochial_num_elementary_scholars = models.PositiveIntegerField(
        null=True, default=0, verbose_name="Number of Elementary Scholars"
    )
    parochial_num_secondary_scholars = models.PositiveIntegerField(
        null=True, default=0, verbose_name="Number of Secondary Scholars"
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
    name = models.CharField(max_length=255)
    is_assistant = models.BooleanField(default=False)
    college = models.CharField(max_length=255, blank=True, null=True)
    theological_seminary = models.CharField(max_length=255, blank=True, null=True)
    num_other_churches_served = models.PositiveIntegerField(default=0, null=True)

    # Record keeping
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "Clergy"
