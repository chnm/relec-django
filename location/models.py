from django.db import models
from simple_history.models import HistoricalRecords


class State(models.Model):
    """
    US State or territory. Uses 2-letter postal code as primary key.
    """

    code = models.CharField(max_length=2, unique=True, primary_key=True)
    name = models.CharField(max_length=50)

    # Record keeping
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.code})"


class County(models.Model):
    """
    County within a state. Keyed by AHCB (Atlas of Historical County Boundaries) ID.
    """

    ahcb_id = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    state = models.ForeignKey(State, on_delete=models.PROTECT, related_name="counties")

    # Record keeping
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ["state", "name"]
        verbose_name_plural = "Counties"
        indexes = [
            models.Index(fields=["state"]),
            models.Index(fields=["name"]),
        ]

    def __str__(self):
        return f"{self.name}, {self.state.code}"


class PopulatedPlace(models.Model):
    """
    A populated place (city, town, village) within a county.
    This model replaces the flat Location model with a proper hierarchy.
    """

    place_id = models.IntegerField(null=True, blank=True, help_text="Apiary ID")
    name = models.CharField(max_length=250)
    county = models.ForeignKey(County, on_delete=models.PROTECT, related_name="places")
    lat = models.FloatField(null=True, blank=True)
    lon = models.FloatField(null=True, blank=True)

    # Migration tracking
    legacy_location_id = models.IntegerField(
        null=True,
        blank=True,
        help_text="ID from original Location model for migration tracking",
    )

    # Record keeping
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ["county", "name"]
        indexes = [
            models.Index(fields=["county"]),
            models.Index(fields=["name"]),
            models.Index(fields=["place_id"]),
            models.Index(fields=["legacy_location_id"]),
        ]

    def __str__(self):
        return f"{self.name}, {self.county.name}, {self.county.state.code}"


class Location(models.Model):
    """
    DEPRECATED: This model represents a geographic location and syncs from Apiary.

    This is the legacy flat location model. New code should use the
    State → County → PopulatedPlace hierarchy instead.

    Kept for backwards compatibility during migration.
    """

    id = models.AutoField(primary_key=True)
    place_id = models.IntegerField(blank=False, null=True)
    state = models.CharField(max_length=2)
    city = models.CharField(max_length=250)
    county = models.CharField(max_length=50)
    map_name = models.CharField(max_length=50)
    county_ahcb = models.CharField(max_length=50)
    lat = models.FloatField()
    lon = models.FloatField()

    # Record keeping
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    class Meta:
        verbose_name = "Location (Legacy)"
        verbose_name_plural = "Locations (Legacy)"

    def __str__(self):
        return f"{self.map_name}, {self.county}, {self.state}"
