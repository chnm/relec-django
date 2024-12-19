from django.db import models
from simple_history.models import HistoricalRecords

from church.models import Church


class SundaySchool(models.Model):
    census_record = models.OneToOneField(
        "census.ReligiousCensusRecord",
        on_delete=models.CASCADE,
        related_name="sunday_school_details",
    )
    church = models.OneToOneField(
        "church.Church", on_delete=models.CASCADE, related_name="sunday_school"
    )
    num_officers_teachers = models.PositiveIntegerField()
    num_scholars = models.PositiveIntegerField()

    # Record keeping
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()


class VacationBibleSchool(models.Model):
    census_record = models.OneToOneField(
        "census.ReligiousCensusRecord",
        on_delete=models.CASCADE,
        related_name="vacation_school_details",
    )
    church = models.ForeignKey(
        "church.Church", on_delete=models.CASCADE, related_name="vacation_bible_school"
    )
    num_officers_teachers = models.PositiveIntegerField(null=True)
    num_scholars = models.PositiveIntegerField(null=True)

    # Record keeping
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()


class ParochialSchool(models.Model):
    census_record = models.OneToOneField(
        "census.ReligiousCensusRecord",
        on_delete=models.CASCADE,
        related_name="parochial_school_details",
    )
    church = models.ForeignKey("church.Church", on_delete=models.CASCADE)
    num_administrators = models.PositiveIntegerField(null=True)
    num_elementary_teachers = models.PositiveIntegerField(null=True)
    num_secondary_teachers = models.PositiveIntegerField(null=True)
    num_elementary_scholars = models.PositiveIntegerField(null=True)
    num_secondary_scholars = models.PositiveIntegerField(null=True)

    # Record keeping
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()
