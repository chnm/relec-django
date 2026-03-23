import django_filters

from .models import ReligiousBody


class ReligiousBodyFilter(django_filters.FilterSet):
    """Filter for ReligiousBody with improved filtering."""

    family_census = django_filters.CharFilter(method="filter_family_census")
    family_relec = django_filters.CharFilter(method="filter_family_relec")

    denomination = django_filters.NumberFilter(field_name="denomination__id")

    def filter_family_census(self, queryset, name, value):
        """Try both possible relationship paths to filter by family_census."""
        # First try direct denomination
        direct_filter = queryset.filter(denomination__family_census=value)
        if direct_filter.exists():
            return direct_filter
        # Then try through census_record
        return queryset.filter(census_record__denomination__family_census=value)

    def filter_family_relec(self, queryset, name, value):
        """Try both possible relationship paths to filter by family_relec."""
        direct_filter = queryset.filter(denomination__family_relec=value)
        if direct_filter.exists():
            return direct_filter
        return queryset.filter(census_record__denomination__family_relec=value)

    class Meta:
        model = ReligiousBody
        fields = [
            "denomination",
            "family_census",
            "family_relec",
        ]
