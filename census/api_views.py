# census/api_views.py
from django.db.models import Count
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

# Cache TTL: 1 hour (data changes infrequently)
API_CACHE_TTL = 60 * 60

from .filters import ReligiousBodyFilter
from .models import Denomination, ReligiousBody
from .serializers import (
    DenominationSerializer,
    ReligiousBodySerializer,
)


@method_decorator(cache_page(API_CACHE_TTL), name="dispatch")
class DenominationViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Denomination.objects.all().order_by("name")
    serializer_class = DenominationSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["family_census", "family_relec"]
    search_fields = ["name"]

    @action(detail=False, methods=["get"])
    def families(self, request):
        """Return unique denomination families for filtering - only those with location data"""
        location_filter = {
            "religiousbody__census_record__populated_place__isnull": False,
        }

        # Single query per family type using aggregation instead of N+1 loop
        census_family_data = (
            Denomination.objects.filter(**location_filter)
            .exclude(family_census__isnull=True)
            .exclude(family_census="")
            .values("family_census")
            .annotate(count=Count("id", distinct=True))
            .order_by("family_census")
        )

        relec_family_data = (
            Denomination.objects.filter(**location_filter)
            .exclude(family_relec__isnull=True)
            .exclude(family_relec="")
            .values("family_relec")
            .annotate(count=Count("id", distinct=True))
            .order_by("family_relec")
        )

        return Response(
            {
                "census_families": [
                    {"name": f["family_census"], "count": f["count"]}
                    for f in census_family_data
                ],
                "relec_families": [
                    {"name": f["family_relec"], "count": f["count"]}
                    for f in relec_family_data
                ],
            }
        )

    @action(detail=False, methods=["get"])
    def by_family(self, request):
        """Return denominations grouped by family - only those with location data"""
        family = request.query_params.get("family_relec", None)

        # Base filter for location data - use new location hierarchy through census_record
        location_filter = {
            "religiousbody__census_record__populated_place__isnull": False,
        }

        if family:
            denominations = (
                Denomination.objects.filter(family_relec=family, **location_filter)
                .distinct()
                .order_by("name")
            )
        else:
            denominations = (
                Denomination.objects.filter(**location_filter)
                .distinct()
                .order_by("family_relec", "name")
            )

        serializer = self.get_serializer(denominations, many=True)
        return Response(serializer.data)


class ReligiousBodyPagination(PageNumberPagination):
    """Custom pagination that includes matched denominations in the response."""

    page_size_query_param = "page_size"
    max_page_size = 5000

    def paginate_queryset(self, queryset, request, view=None):
        # Extract distinct denomination names from the full filtered queryset
        # before pagination slices it
        self.matched_denominations = list(
            queryset.filter(denomination__isnull=False)
            .values_list("denomination__name", flat=True)
            .distinct()
            .order_by("denomination__name")
        )
        return super().paginate_queryset(queryset, request, view)

    def get_paginated_response(self, data):
        from collections import OrderedDict

        return Response(
            OrderedDict(
                [
                    ("count", self.page.paginator.count),
                    ("denominations", self.matched_denominations),
                    ("next", self.get_next_link()),
                    ("previous", self.get_previous_link()),
                    ("results", data),
                ]
            )
        )


@method_decorator(cache_page(API_CACHE_TTL), name="dispatch")
class ReligiousBodyViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Consolidated congregation-level endpoint.

    Returns all congregation data including location, denomination, membership,
    finances, pastors, transcription status, and schedule IDs.

    Query Parameters:
        - denomination: Filter by denomination ID (integer)
        - family_census: Filter by census family name
        - family_relec: Filter by RelEc family name
        - transcription_status: Filter by transcription status (e.g., 'approved')
        - exclude_families: Comma-separated census families to exclude
        - urban_rural: Filter by 'urban' or 'rural'
        - bounds: Geographic bounding box as 'south,west,north,east'
        - search: Search by name, address, or census code
        - limit: Page size (use page_size query param)
    """

    queryset = (
        ReligiousBody.objects.all()
        .select_related(
            "denomination",
            "census_record",
            "census_record__county__state",
            "census_record__populated_place",
        )
        .prefetch_related("membership", "census_record__clergy")
        .order_by("census_record__schedule_id")
    )
    serializer_class = ReligiousBodySerializer
    pagination_class = ReligiousBodyPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = ReligiousBodyFilter
    search_fields = ["name", "address", "census_code"]
    ordering_fields = ["census_record__schedule_id", "name"]
    ordering = ["census_record__schedule_id"]

    @action(detail=False, methods=["get"])
    def denomination_families(self, request):
        """
        List unique denomination families with counts.

        Returns both census families and RelEc families, with counts of denominations
        and congregations in each family. Uses aggregation to avoid N+1 queries.
        """
        from django.db.models import Q

        # Census families — single query with all counts
        census_families_data = (
            Denomination.objects.filter(family_census__isnull=False)
            .exclude(family_census="")
            .values("family_census")
            .annotate(
                denomination_count=Count("id", distinct=True),
                total_congregation_count=Count("religiousbody", distinct=True),
                congregation_count_with_location=Count(
                    "religiousbody",
                    distinct=True,
                    filter=Q(religiousbody__census_record__populated_place__isnull=False),
                ),
            )
            .order_by("family_census")
        )

        # RelEc families — single query with all counts
        relec_families_data = (
            Denomination.objects.filter(family_relec__isnull=False)
            .exclude(family_relec="")
            .values("family_relec")
            .annotate(
                denomination_count=Count("id", distinct=True),
                total_congregation_count=Count("religiousbody", distinct=True),
                congregation_count_with_location=Count(
                    "religiousbody",
                    distinct=True,
                    filter=Q(religiousbody__census_record__populated_place__isnull=False),
                ),
            )
            .order_by("family_relec")
        )

        return Response(
            {
                "census_families": [
                    {
                        "name": f["family_census"],
                        "denominations": f["denomination_count"],
                        "congregations": f["congregation_count_with_location"],
                        "total_congregations": f["total_congregation_count"],
                        "has_location_data": f["congregation_count_with_location"] > 0,
                    }
                    for f in census_families_data
                ],
                "relec_families": [
                    {
                        "name": f["family_relec"],
                        "denominations": f["denomination_count"],
                        "congregations": f["congregation_count_with_location"],
                        "total_congregations": f["total_congregation_count"],
                        "has_location_data": f["congregation_count_with_location"] > 0,
                    }
                    for f in relec_families_data
                ],
            }
        )
