# census/api_views.py
from django.db.models import IntegerField, Sum, Value
from django.db.models.functions import Coalesce
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .filters import ReligiousBodyFilter
from .models import Denomination, ReligiousBody
from .serializers import (
    DenominationSerializer,
    MapMarkerSerializer,
    ReligiousBodySerializer,
)


class DenominationViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Denomination.objects.all().order_by("name")
    serializer_class = DenominationSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["family_census", "family_arda"]
    search_fields = ["name"]

    @action(detail=False, methods=["get"])
    def families(self, request):
        """Return unique denomination families for filtering"""
        census_families = (
            Denomination.objects.values_list("family_census", flat=True)
            .distinct()
            .order_by("family_census")
        )
        arda_families = (
            Denomination.objects.values_list("family_arda", flat=True)
            .distinct()
            .order_by("family_arda")
        )

        # Count denominations in each family for display purposes
        family_counts = {}
        for family in census_families:
            if family:  # Skip empty family names
                count = Denomination.objects.filter(family_census=family).count()
                family_counts[family] = count

        return Response(
            {
                "census_families": [
                    {"name": family, "count": family_counts.get(family, 0)}
                    for family in census_families
                    if family
                ],
                "arda_families": list(arda_families),
            }
        )

    @action(detail=False, methods=["get"])
    def by_family(self, request):
        """Return denominations grouped by family"""
        family = request.query_params.get("family_census", None)

        if family:
            denominations = Denomination.objects.filter(family_census=family).order_by(
                "name"
            )
        else:
            denominations = Denomination.objects.all().order_by("family_census", "name")

        serializer = self.get_serializer(denominations, many=True)
        return Response(serializer.data)


class ReligiousBodyViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = (
        ReligiousBody.objects.all()
        .select_related("location", "denomination", "census_record")
        .prefetch_related("census_record__clergy")
    )
    serializer_class = ReligiousBodySerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_class = ReligiousBodyFilter
    search_fields = ["name", "address", "census_code"]

    @action(detail=False, methods=["get"])
    def map_data(self, request):
        """Optimized geodata endpoint for map display with robust error handling"""
        try:
            # Start with base queryset - only select what we need
            queryset = ReligiousBody.objects.filter(
                location__isnull=False
            ).select_related("location", "denomination")

            # Apply filtering with explicit logging and error handling
            if "family_census" in request.query_params:
                family_census = request.query_params.get("family_census")
                print(f"Filtering by family_census: {family_census}")
                try:
                    queryset = queryset.filter(
                        denomination__family_census=family_census
                    )
                except Exception as e:
                    print(f"Error filtering by family_census: {e}")
                    # Continue with unfiltered queryset instead of failing

            # Add denomination filtering
            if "denomination" in request.query_params:
                denomination_id = request.query_params.get("denomination")
                print(f"Filtering by denomination_id: {denomination_id}")
                try:
                    queryset = queryset.filter(denomination_id=denomination_id)
                except Exception as e:
                    print(f"Error filtering by denomination_id: {e}")
                    # Continue with previously filtered queryset

            # Add bounds filtering if present
            if "bounds" in request.query_params:
                bounds = request.query_params.get("bounds")
                try:
                    south, west, north, east = map(float, bounds.split(","))
                    queryset = queryset.filter(
                        location__lat__gte=south,
                        location__lat__lte=north,
                        location__lon__gte=west,
                        location__lon__lte=east,
                    )
                    print(f"Applied bounds filter: {bounds}")
                except Exception as e:
                    print(f"Error applying bounds filter: {e}")

            try:
                # Try to annotate total_members, preferring the recorded total if available
                queryset = queryset.annotate(
                    total_members=Coalesce(
                        # First try to use the recorded total
                        "membership__total_members_by_sex",
                        # Then try to calculate from male/female components
                        Sum(
                            Coalesce("membership__male_members", 0)
                            + Coalesce("membership__female_members", 0)
                        ),
                        # Default to 0 if none of the above is available
                        Value(0),
                        output_field=IntegerField(),
                    )
                )
            except Exception as e:
                print(f"Error annotating total_members: {e}")
                # If annotation fails, fall back to a simpler query
                queryset = queryset.annotate(
                    total_members=Value(0, output_field=IntegerField())
                )

            # Add a reasonable limit to prevent overloading
            queryset = queryset[:2000]

            # Use the lightweight serializer
            serializer = MapMarkerSerializer(queryset, many=True)
            data = serializer.data

            print(f"Returning {len(data)} map markers")
            return Response(data)

        except Exception as e:
            import traceback

            print(f"Exception in map_data: {e}")
            print(traceback.format_exc())
            return Response(
                {"error": str(e), "traceback": traceback.format_exc()}, status=500
            )
