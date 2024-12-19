from django.db import models
from simple_history.models import HistoricalRecords


class Denomination(models.Model):
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=50, unique=True)
    history = HistoricalRecords()

    # Record keeping
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    def __str__(self):
        return self.name


class ReligiousCensusRecord(models.Model):
    """
    This model serves as the primary record that ties together all related data
    for a specific church census entry.
    """

    resource_id = models.IntegerField(unique=True)
    denomination = models.ForeignKey(Denomination, on_delete=models.PROTECT)
    schedule_title = models.CharField(max_length=255)
    schedule_id = models.CharField(max_length=50)

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
