import django_filters
from django.db.models import OuterRef, Q, Subquery

from .models import ReligiousBody, ScheduleReconciliation


class ReligiousBodyFilter(django_filters.FilterSet):
    """Filter for ReligiousBody with improved filtering."""

    family_census = django_filters.CharFilter(method="filter_family_census")
    family_relec = django_filters.CharFilter(method="filter_family_relec")
    denomination = django_filters.NumberFilter(field_name="denomination__id")
    transcription_status = django_filters.CharFilter(
        field_name="census_record__transcription_status"
    )
    exclude_families = django_filters.CharFilter(method="filter_exclude_families")
    urban_rural = django_filters.CharFilter(method="filter_urban_rural")
    bounds = django_filters.CharFilter(method="filter_bounds")
    has_location = django_filters.BooleanFilter(method="filter_has_location")
    corrected = django_filters.BooleanFilter(method="filter_corrected")

    def filter_corrected(self, queryset, name, value):
        """Filter by whether the latest reconciliation outcome is mixed."""
        latest_outcome = (
            ScheduleReconciliation.objects.filter(
                census_schedule=OuterRef("census_record")
            )
            .order_by("-applied_at", "-pk")
            .values("outcome")[:1]
        )
        queryset = queryset.annotate(_latest_outcome=Subquery(latest_outcome))
        mixed = ScheduleReconciliation.Outcome.MIXED
        if value:
            return queryset.filter(_latest_outcome=mixed)
        return queryset.filter(
            Q(_latest_outcome__isnull=True) | ~Q(_latest_outcome=mixed)
        )

    def filter_has_location(self, queryset, name, value):
        """Filter by whether the congregation has location data."""
        if value:
            return queryset.filter(census_record__populated_place__isnull=False)
        return queryset.filter(census_record__populated_place__isnull=True)

    def filter_family_census(self, queryset, name, value):
        """Filter by family_census via direct denomination or schedule denomination."""
        return queryset.filter(
            Q(denomination__family_census=value)
            | Q(census_record__schedule_denomination__family_census=value)
        ).distinct()

    def filter_family_relec(self, queryset, name, value):
        """Filter by family_relec via direct denomination or schedule denomination."""
        return queryset.filter(
            Q(denomination__family_relec=value)
            | Q(census_record__schedule_denomination__family_relec=value)
        ).distinct()

    def filter_exclude_families(self, queryset, name, value):
        """Exclude specific denomination families (comma-separated)."""
        families = [f.strip() for f in value.split(",") if f.strip()]
        if families:
            queryset = queryset.exclude(
                Q(denomination__family_census__in=families)
                | Q(
                    census_record__schedule_denomination__family_census__in=families
                )
            )
        return queryset

    def filter_urban_rural(self, queryset, name, value):
        """Filter by urban/rural status."""
        if value.lower() == "urban":
            # "U+" is a U the enumerator marked with a plus; still urban.
            return queryset.filter(urban_rural_code__in=["U", "U+"])
        elif value.lower() == "rural":
            return queryset.filter(urban_rural_code="R")
        return queryset

    def filter_bounds(self, queryset, name, value):
        """Filter by geographic bounding box as 'south,west,north,east'."""
        try:
            south, west, north, east = map(float, value.split(","))
            return queryset.filter(
                census_record__populated_place__lat__gte=south,
                census_record__populated_place__lat__lte=north,
                census_record__populated_place__lon__gte=west,
                census_record__populated_place__lon__lte=east,
            )
        except (ValueError, TypeError):
            return queryset

    class Meta:
        model = ReligiousBody
        fields = [
            "denomination",
            "family_census",
            "family_relec",
            "transcription_status",
            "exclude_families",
            "urban_rural",
            "bounds",
            "has_location",
            "corrected",
        ]
