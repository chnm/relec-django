import json

from import_export import fields, resources
from import_export.widgets import ForeignKeyWidget

from census.models import CensusSchedule
from .models import DataLayer


class LenientForeignKeyWidget(ForeignKeyWidget):
    """FK widget that returns None instead of raising on missing records."""

    def clean(self, value, row=None, **kwargs):
        if not value:
            return None
        try:
            return super().clean(value, row=row, **kwargs)
        except self.model.DoesNotExist:
            return None


class DataLayerResource(resources.ModelResource):
    """
    Import/Export resource for DataLayer.

    Known columns map to model fields. Any extra columns in the CSV
    are collected into the JSONB `data` field automatically on import.

    Expected CSV headers (all optional except title):
        title, lat, lon, city, county, state, source, resource_id, data

    Any columns not in the list above are stored as keys in `data`.
    The `resource_id` column looks up CensusSchedule by resource_id.
    If the schedule doesn't exist, the field is set to None.
    """

    census_schedule = fields.Field(
        column_name="resource_id",
        attribute="census_schedule",
        widget=LenientForeignKeyWidget(CensusSchedule, field="resource_id"),
    )

    class Meta:
        model = DataLayer
        fields = (
            "id",
            "title",
            "lat",
            "lon",
            "city",
            "county",
            "state",
            "source",
            "census_schedule",
            "data",
        )
        import_id_fields = ("title", "source")
        skip_unchanged = True
        report_skipped = False

    # Known model columns (excluding `data` and `census_schedule` which are handled separately)
    KNOWN_COLUMNS = {"id", "title", "lat", "lon", "city", "county", "state", "source", "resource_id", "data"}

    def before_import_row(self, row, **kwargs):
        """Collect any extra columns into the `data` JSON field."""
        extra = {}
        for key in list(row.keys()):
            if key not in self.KNOWN_COLUMNS:
                value = row[key]
                if value is not None and value != "":
                    extra[key] = value

        # Merge extras with any existing `data` value
        existing_data = row.get("data", "")
        if existing_data and isinstance(existing_data, str):
            try:
                existing_data = json.loads(existing_data)
            except (json.JSONDecodeError, ValueError):
                existing_data = {}
        elif not isinstance(existing_data, dict):
            existing_data = {}

        existing_data.update(extra)
        row["data"] = json.dumps(existing_data) if existing_data else "{}"
