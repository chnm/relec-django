from django.db import models
from simple_history.models import HistoricalRecords

from census.models import ReligiousCensusRecord
from location.models import City, County, State, UnlistedLocation


class Church(models.Model):
    census_record = models.OneToOneField(
        "census.ReligiousCensusRecord",
        on_delete=models.CASCADE,
        related_name="church_details",
    )
    name = models.CharField(max_length=255, verbose_name="Local Church Name")
    census_code = models.CharField(max_length=50)
    division = models.CharField(max_length=100)

    # Location fields
    state = models.ForeignKey("location.State", on_delete=models.PROTECT)
    county = models.ForeignKey(
        "location.County", on_delete=models.PROTECT, null=True, blank=True
    )
    city = models.ForeignKey(
        "location.City", on_delete=models.PROTECT, null=True, blank=True
    )
    unlisted_location = models.ForeignKey(
        "location.UnlistedLocation", on_delete=models.PROTECT, null=True, blank=True
    )
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
        "census.ReligiousCensusRecord",
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
