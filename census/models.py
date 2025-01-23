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

    resource_id = models.IntegerField(unique=True)
    denomination = models.ForeignKey(Denomination, on_delete=models.PROTECT)
    schedule_title = models.CharField(max_length=255)
    schedule_id = models.CharField(max_length=50)
    location = models.ForeignKey(Location, on_delete=models.PROTECT, default=None)

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

    # Sunday school
    sunday_school_num_officers_teachers = models.PositiveIntegerField()
    sunday_school_num_scholars = models.PositiveIntegerField()

    # Vacation Bible school
    vbs_num_officers_teachers = models.PositiveIntegerField(null=True)
    vbs_num_scholars = models.PositiveIntegerField(null=True)

    # Parochial school
    parochial_num_administrators = models.PositiveIntegerField(null=True)
    parochial_num_elementary_teachers = models.PositiveIntegerField(null=True)
    parochial_num_secondary_teachers = models.PositiveIntegerField(null=True)
    parochial_num_elementary_scholars = models.PositiveIntegerField(null=True)
    parochial_num_secondary_scholars = models.PositiveIntegerField(null=True)

    # Finances
    expenses = models.DecimalField(max_digits=12, decimal_places=2)
    benevolences = models.DecimalField(max_digits=12, decimal_places=2)
    total_expenditures = models.DecimalField(max_digits=12, decimal_places=2)

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
        return f"Census Record {self.resource_id} - {self.denomination}"


class Church(models.Model):
    census_record = models.OneToOneField(
        "census.CensusSchedule",
        on_delete=models.CASCADE,
        related_name="church_details",
    )
    name = models.CharField(max_length=255, verbose_name="Local Church Name")
    census_code = models.CharField(max_length=50)
    division = models.CharField(max_length=100)

    # Location fields
    location = models.ForeignKey(Location, on_delete=models.CASCADE)
    address = models.CharField(max_length=255, null=True, blank=True)
    urban_rural_code = models.CharField(max_length=50)

    # Church property details
    num_edifices = models.PositiveIntegerField(default=0, blank=True, null=True)
    edifice_value = models.DecimalField(
        max_digits=12, decimal_places=2, blank=True, null=True
    )
    edifice_debt = models.DecimalField(
        max_digits=12, decimal_places=2, blank=True, null=True
    )

    # Parsonage details
    has_pastors_residence = models.BooleanField(default=False)
    residence_value = models.DecimalField(max_digits=12, decimal_places=2, null=True)
    residence_debt = models.DecimalField(max_digits=12, decimal_places=2, null=True)

    # Record keeping
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    class Meta:
        verbose_name = "Church"
        verbose_name_plural = "Churches"


class Membership(models.Model):
    census_record = models.OneToOneField(
        "census.CensusSchedule",
        on_delete=models.CASCADE,
        related_name="membership_details",
    )
    church = models.OneToOneField(
        "Church", on_delete=models.CASCADE, related_name="membership"
    )
    male_members = models.PositiveIntegerField(default=0)
    female_members = models.PositiveIntegerField(default=0)
    members_under_13 = models.PositiveIntegerField(default=0)
    members_13_and_older = models.PositiveIntegerField(default=0)

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
    num_other_churches_served = models.PositiveIntegerField(default=0)

    # Record keeping
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "Clergy"
