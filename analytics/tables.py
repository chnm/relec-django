import django_tables2 as tables
from django.utils.html import format_html

from census.models import ReligiousBody


class ReligiousBodyTable(tables.Table):
    """Table for displaying Religious Body query results with sorting and pagination"""

    schedule_id = tables.Column(
        accessor="census_record__schedule_id",
        verbose_name="Schedule ID",
        order_by="census_record__schedule_id",
    )

    name = tables.Column(
        verbose_name="Religious Body",
        empty_values=(),
    )

    denomination = tables.Column(
        accessor="denomination__name",
        verbose_name="Denomination",
        order_by="denomination__name",
    )

    location = tables.Column(
        empty_values=(),
        verbose_name="Location",
        orderable=False,
    )

    num_edifices = tables.Column(
        verbose_name="Edifices",
        order_by="num_edifices",
    )

    edifice_value = tables.Column(
        verbose_name="Value",
        order_by="edifice_value",
    )

    transcription_status = tables.Column(
        accessor="census_record__transcription_status",
        verbose_name="Status",
        order_by="census_record__transcription_status",
    )

    actions = tables.Column(
        empty_values=(),
        verbose_name="Actions",
        orderable=False,
    )

    def render_name(self, value, record):
        """Render religious body name with fallback"""
        if value:
            return value
        return format_html('<em class="text-gray-400">Unnamed</em>')

    def render_location(self, record):
        """Render location as city, county, state"""
        if record.location:
            parts = []
            if record.location.city:
                parts.append(record.location.city)
            if record.location.county:
                parts.append(record.location.county)
            if record.location.state:
                parts.append(record.location.state)
            return ", ".join(parts) if parts else "—"
        return format_html('<span class="text-gray-400">No location</span>')

    def render_num_edifices(self, value):
        """Render edifices with fallback"""
        return value if value is not None else "—"

    def render_edifice_value(self, value):
        """Render value as currency"""
        if value is not None:
            return f"${value:,.2f}"
        return "—"

    def render_transcription_status(self, value, record):
        """Render status as badge"""
        if not record.census_record:
            return "—"

        status_classes = {
            "approved": "bg-green-100 text-green-800",
            "completed": "bg-blue-100 text-blue-800",
            "in_progress": "bg-yellow-100 text-yellow-800",
        }
        css_class = status_classes.get(value, "bg-gray-100 text-gray-800")
        display = record.census_record.get_transcription_status_display()

        return format_html(
            '<span class="px-2 py-1 text-xs rounded-full {}">{}</span>',
            css_class,
            display,
        )

    def render_actions(self, record):
        """Render admin link"""
        if record.census_record:
            return format_html(
                '<a href="/admin/census/censusschedule/{}/change/" target="_blank" '
                'class="text-religious-primary hover:text-primary-700">'
                "Edit in Admin &rarr;</a>",
                record.census_record.id,
            )
        return ""

    class Meta:
        model = ReligiousBody
        template_name = "analytics/table.html"
        fields = (
            "schedule_id",
            "name",
            "denomination",
            "location",
            "num_edifices",
            "edifice_value",
            "transcription_status",
            "actions",
        )
        attrs = {
            "class": "min-w-full divide-y divide-gray-200",
            "thead": {
                "class": "bg-gray-50",
            },
            "tbody": {
                "class": "bg-white divide-y divide-gray-200",
            },
        }
        row_attrs = {
            "class": "hover:bg-gray-50",
        }
