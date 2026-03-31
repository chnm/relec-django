import django_filters

from .models import ReligiousBody


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

    def filter_has_location(self, queryset, name, value):
        """Filter by whether the congregation has location data."""
        if value:
            return queryset.filter(census_record__populated_place__isnull=False)
        return queryset.filter(census_record__populated_place__isnull=True)

    def filter_family_census(self, queryset, name, value):
        """Filter by family_census via direct denomination or schedule denomination."""
        direct_filter = queryset.filter(denomination__family_census=value)
        if direct_filter.exists():
            return direct_filter
        return queryset.filter(
            census_record__schedule_denomination__family_census=value
        )

    def filter_family_relec(self, queryset, name, value):
        """Filter by family_relec via direct denomination or schedule denomination."""
        direct_filter = queryset.filter(denomination__family_relec=value)
        if direct_filter.exists():
            return direct_filter
        return queryset.filter(
            census_record__schedule_denomination__family_relec=value
        )

    def filter_exclude_families(self, queryset, name, value):
        """Exclude specific denomination families (comma-separated)."""
        families = [f.strip() for f in value.split(",") if f.strip()]
        if families:
            queryset = queryset.exclude(denomination__family_census__in=families)
        return queryset

    def filter_urban_rural(self, queryset, name, value):
        """Filter by urban/rural status."""
        if value.lower() == "urban":
            return queryset.filter(urban_rural_code="Urban")
        elif value.lower() == "rural":
            return queryset.filter(urban_rural_code="Rural")
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
        ]
