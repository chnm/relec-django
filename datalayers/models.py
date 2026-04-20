from django.db import models


class DataLayer(models.Model):
    """
    A bespoke data point that can be linked to a census schedule.

    Use the JSONB `data` field for visualization-specific attributes that
    vary across datasets (e.g., pastor_name, pastor_gender, notes for the
    spiritualist map; or address, zip_code for church location data).

    Structured fields (title, lat/lon, location info, schedule FK) are
    available for filtering, indexing, and cross-referencing with census data.
    """

    title = models.CharField(max_length=255, help_text="Name of the church or data point")
    lat = models.FloatField(null=True, blank=True)
    lon = models.FloatField(null=True, blank=True)

    # Location fields for filtering/display
    city = models.CharField(max_length=255, blank=True)
    county = models.CharField(max_length=255, blank=True)
    state = models.CharField(max_length=255, blank=True)

    # Optional link to a census schedule
    census_schedule = models.ForeignKey(
        "census.CensusSchedule",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="data_layers",
        help_text="Link to a census schedule record, if applicable",
    )

    # Source dataset identifier (e.g., "spiritualist-pastors", "dc-churches")
    source = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
        help_text="Identifier for the dataset this point belongs to",
    )

    # Flexible JSONB field for bespoke data
    data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Arbitrary key-value data for this point (e.g., pastor_name, gender, notes)",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["source", "title"]
        verbose_name = "Data Layer"
        verbose_name_plural = "Data Layers"
        indexes = [
            models.Index(fields=["source"]),
            models.Index(fields=["state", "county"]),
        ]

    def __str__(self):
        return self.title
