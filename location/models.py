from django.db import models
from simple_history.models import HistoricalRecords


class Location(models.Model):
    """
    This model represents a geographic location and syncs from Apiary.
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

    def __str__(self):
        return f"{self.map_name}, {self.county}, {self.state}"
