from django.db import models
from simple_history.models import HistoricalRecords


class State(models.Model):
    name = models.CharField(max_length=100)
    abbreviation = models.CharField(max_length=2)

    # Record keeping
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class County(models.Model):
    name = models.CharField(max_length=100)
    state = models.ForeignKey(State, on_delete=models.PROTECT, related_name="counties")

    # Record keeping
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ["state", "name"]
        verbose_name_plural = "counties"
        unique_together = ["name", "state"]

    def __str__(self):
        return f"{self.name}, {self.state.abbreviation}"


class City(models.Model):
    name = models.CharField(max_length=100)
    state = models.ForeignKey(State, on_delete=models.PROTECT, related_name="cities")
    county = models.ForeignKey(
        County,
        on_delete=models.PROTECT,
        related_name="cities",
        null=True,  # Some historical places might not have county data
        blank=True,
    )

    # Record keeping
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ["state", "name"]
        verbose_name_plural = "cities"
        unique_together = ["name", "state"]

    def __str__(self):
        return f"{self.name}, {self.state.abbreviation}"


class UnlistedLocation(models.Model):
    """
    For handling historical or unofficial place names that don't match
    standard geographic designations
    """

    name = models.CharField(max_length=255)
    state = models.ForeignKey(
        State, on_delete=models.PROTECT, related_name="unlisted_locations"
    )
    county = models.ForeignKey(
        County,
        on_delete=models.PROTECT,
        related_name="unlisted_locations",
        null=True,
        blank=True,
    )
    notes = models.TextField(blank=True)

    # Record keeping
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ["state", "name"]
        unique_together = ["name", "state"]

    def __str__(self):
        return f"{self.name}, {self.state.abbreviation}"
