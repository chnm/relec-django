from django.db import models
from simple_history.models import HistoricalRecords

from church.models import Church


class Clergy(models.Model):
    census_record = models.ForeignKey(
        "census.ReligiousCensusRecord", on_delete=models.CASCADE, related_name="clergy"
    )
    church = models.ForeignKey(
        'church.Church',
        on_delete=models.CASCADE,
        related_name='pastors'
    )
    name = models.CharField(max_length=255)
    church = models.ForeignKey("church.Church", on_delete=models.CASCADE)
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
