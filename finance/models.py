# finances/models.py
from django.db import models
from simple_history.models import HistoricalRecords

from church.models import Church
from census.models import ReligiousCensusRecord


class AnnualFinancialRecord(models.Model):
    census_record = models.OneToOneField(
        "census.ReligiousCensusRecord",
        on_delete=models.CASCADE,
        related_name="financial_record",
    )
    church = models.ForeignKey("church.Church", on_delete=models.CASCADE)
    year = models.PositiveIntegerField()
    expenses = models.DecimalField(max_digits=12, decimal_places=2)
    benevolences = models.DecimalField(max_digits=12, decimal_places=2)
    total_expenditures = models.DecimalField(max_digits=12, decimal_places=2)

    # Record keeping
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()
