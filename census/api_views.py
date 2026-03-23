# census/api_views.py
import requests
from django.db.models import IntegerField, Sum, Value
from django.db.models.functions import Coalesce
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

# Cache TTL: 1 hour (data changes infrequently)
API_CACHE_TTL = 60 * 60

from .filters import ReligiousBodyFilter
from .models import Denomination, ReligiousBody
from .serializers import (
    DemographicsMapSerializer,
    DenominationSerializer,
    MapMarkerSerializer,
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
        # Get families that have at least one ReligiousBody with location data
        # Filter through census_record -> populated_place for the new location hierarchy
        census_families = (
            Denomination.objects.filter(
                religiousbody__census_record__populated_place__isnull=False,
            )
            .values_list("family_census", flat=True)
            .distinct()
            .order_by("family_census")
        )

        relec_families = (
            Denomination.objects.filter(
                religiousbody__census_record__populated_place__isnull=False,
            )
            .values_list("family_relec", flat=True)
            .distinct()
            .order_by("family_relec")
        )

        # Count denominations in each census family that have location data
        census_family_counts = {}
        for family in census_families:
            if family:  # Skip empty family names
                count = (
                    Denomination.objects.filter(
                        family_census=family,
                        religiousbody__census_record__populated_place__isnull=False,
                    )
                    .distinct()
                    .count()
                )
                census_family_counts[family] = count

        # Count denominations in each RelEc family that have location data
        relec_family_counts = {}
        for family in relec_families:
            if family:  # Skip empty family names
                count = (
                    Denomination.objects.filter(
                        family_relec=family,
                        religiousbody__census_record__populated_place__isnull=False,
                    )
                    .distinct()
                    .count()
                )
                relec_family_counts[family] = count

        return Response(
            {
                "census_families": [
                    {"name": family, "count": census_family_counts.get(family, 0)}
                    for family in census_families
                    if family
                ],
                "relec_families": [
                    {"name": family, "count": relec_family_counts.get(family, 0)}
                    for family in relec_families
                    if family
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


@method_decorator(cache_page(API_CACHE_TTL), name="dispatch")
class ReligiousBodyViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = (
        ReligiousBody.objects.all()
        .select_related(
            "denomination",
            "census_record",
            "census_record__county__state",
            "census_record__populated_place",
        )
        .order_by("census_record__schedule_id")
    )
    serializer_class = ReligiousBodySerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = ReligiousBodyFilter
    search_fields = ["name", "address", "census_code"]
    ordering_fields = ["census_record__schedule_id", "name"]
    ordering = ["census_record__schedule_id"]

    @action(detail=False, methods=["get"])
    def map_data(self, request):
        """Optimized geodata endpoint for map display with robust error handling"""
        try:
            # Start with base queryset - only select what we need
            queryset = ReligiousBody.objects.filter(
                census_record__populated_place__isnull=False
            ).select_related(
                "census_record__populated_place",
                "census_record__county__state",
                "denomination",
            )

            # Apply filtering - support both family_relec and family_census
            if "family_relec" in request.query_params:
                family_relec = request.query_params.get("family_relec")
                queryset = queryset.filter(
                    denomination__family_relec=family_relec
                )
            elif "family_census" in request.query_params:
                family_census = request.query_params.get("family_census")
                queryset = queryset.filter(
                    denomination__family_census=family_census
                )

            # Add denomination filtering
            if "denomination" in request.query_params:
                denomination_id = request.query_params.get("denomination")
                queryset = queryset.filter(denomination_id=denomination_id)

            # Add bounds filtering if present
            if "bounds" in request.query_params:
                bounds = request.query_params.get("bounds")
                try:
                    south, west, north, east = map(float, bounds.split(","))
                    queryset = queryset.filter(
                        census_record__populated_place__lat__gte=south,
                        census_record__populated_place__lat__lte=north,
                        census_record__populated_place__lon__gte=west,
                        census_record__populated_place__lon__lte=east,
                    )
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

            # Apply optional limit
            limit = min(int(request.query_params.get("limit", 5000)), 5000)
            queryset = queryset[:limit]

            # Use the lightweight serializer
            serializer = MapMarkerSerializer(queryset, many=True)
            data = serializer.data

            return Response(data)

        except Exception as e:
            import traceback

            print(f"Exception in map_data: {e}")
            print(traceback.format_exc())
            return Response(
                {"error": str(e), "traceback": traceback.format_exc()}, status=500
            )

    @action(detail=False, methods=["get"])
    def demographics_data(self, request):
        """
        Demographics endpoint with membership data for map display.

        Query Parameters:
            - family_relec: Filter by RelEc denomination family
            - family_census: Filter by census denomination family
            - denomination: Filter by denomination ID
            - bounds: Bounding box as "south,west,north,east"
            - transcription_status: Filter by status (default: "approved")
            - limit: Maximum number of records (default: 5000, max: 5000)
        """
        try:
            # Start with base queryset - only select what we need for demographics
            queryset = (
                ReligiousBody.objects.filter(
                    census_record__populated_place__isnull=False
                )
                .select_related(
                    "census_record__populated_place",
                    "census_record__county__state",
                    "denomination",
                )
                .prefetch_related("membership")
            )

            # Apply filtering - support both family_relec and family_census
            if "family_relec" in request.query_params:
                family_relec = request.query_params.get("family_relec")
                queryset = queryset.filter(
                    denomination__family_relec=family_relec
                )
            elif "family_census" in request.query_params:
                family_census = request.query_params.get("family_census")
                queryset = queryset.filter(
                    denomination__family_census=family_census
                )

            # Add denomination filtering
            if "denomination" in request.query_params:
                denomination_id = request.query_params.get("denomination")
                queryset = queryset.filter(denomination_id=denomination_id)

            # Add bounds filtering if present
            if "bounds" in request.query_params:
                bounds = request.query_params.get("bounds")
                try:
                    south, west, north, east = map(float, bounds.split(","))
                    queryset = queryset.filter(
                        census_record__populated_place__lat__gte=south,
                        census_record__populated_place__lat__lte=north,
                        census_record__populated_place__lon__gte=west,
                        census_record__populated_place__lon__lte=east,
                    )
                except (ValueError, TypeError):
                    pass

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

            # Filter by transcription status (default to approved for verified data)
            transcription_status = request.query_params.get(
                "transcription_status", "approved"
            )
            if transcription_status:
                queryset = queryset.filter(
                    census_record__transcription_status=transcription_status
                )

            # Apply optional limit
            limit = min(int(request.query_params.get("limit", 5000)), 5000)
            queryset = queryset[:limit]

            # Use the demographics serializer
            serializer = DemographicsMapSerializer(queryset, many=True)
            data = serializer.data

            return Response(data)

        except Exception as e:
            import traceback

            print(f"Exception in demographics_data: {e}")
            print(traceback.format_exc())
            return Response(
                {"error": str(e), "traceback": traceback.format_exc()}, status=500
            )

    @action(detail=False, methods=["get"])
    def geojson(self, request):
        """
        GeoJSON endpoint for mapping denominations by populated place.
        Returns proper GeoJSON FeatureCollection format with congregations (ReligiousBody)
        mapped to their populated place lat/lon.

        Each feature represents a congregation (ReligiousBody) with coordinates from its
        associated populated place (Location). Multiple congregations of the same denomination
        may share the same populated place coordinates.

        Query Parameters:
            - denomination: Specific denomination ID(s) - supports multiple
            - family_census: Filter by census denomination family
            - family_relec: Filter by RelEc denomination family
            - exclude_families: Comma-separated list of families to exclude
            - transcription_status: Only include schedules with this status (e.g., 'approved')
            - bounds: Optional bounding box as "south,west,north,east"
            - limit: Maximum number of features to return (default: 2000)
        """
        try:
            # Start with base queryset - ReligiousBody (congregations) with populated place coordinates
            queryset = ReligiousBody.objects.filter(
                census_record__populated_place__isnull=False,
                census_record__populated_place__lat__isnull=False,
                census_record__populated_place__lon__isnull=False,
            ).select_related(
                "census_record__populated_place__county__state",
                "census_record__county__state",
                "denomination",
            )

            # Filter by denomination family (census)
            if "family_census" in request.query_params:
                family_census = request.query_params.getlist("family_census")
                # Only filter if we have non-empty values
                if family_census and any(f for f in family_census if f):
                    queryset = queryset.filter(
                        denomination__family_census__in=family_census
                    )
            # Filter by denomination family (relec)
            if "family_relec" in request.query_params:
                family_relec = request.query_params.getlist("family_relec")
                # Only filter if we have non-empty values
                if family_relec and any(f for f in family_relec if f):
                    queryset = queryset.filter(
                        denomination__family_relec__in=family_relec
                    )

            # Exclude specific families (for filtering out major denominations)
            if "exclude_families" in request.query_params:
                exclude = request.query_params.get("exclude_families").split(",")
                queryset = queryset.exclude(denomination__family_census__in=exclude)

            # Filter by specific denomination(s) - supports multiple IDs
            if "denomination" in request.query_params:
                denomination_ids = request.query_params.getlist("denomination")
                # Only filter if we have non-empty values
                if denomination_ids and any(d for d in denomination_ids if d):
                    queryset = queryset.filter(denomination_id__in=denomination_ids)

            # Filter by transcription status (e.g., only show fully transcribed congregations)
            if "transcription_status" in request.query_params:
                status = request.query_params.get("transcription_status")
                if status:  # Only filter if status is not empty
                    queryset = queryset.filter(
                        census_record__transcription_status=status
                    )

            # Apply bounding box filter if provided
            if "bounds" in request.query_params:
                bounds = request.query_params.get("bounds")
                try:
                    south, west, north, east = map(float, bounds.split(","))
                    queryset = queryset.filter(
                        census_record__populated_place__lat__gte=south,
                        census_record__populated_place__lat__lte=north,
                        census_record__populated_place__lon__gte=west,
                        census_record__populated_place__lon__lte=east,
                    )
                except (ValueError, TypeError) as e:
                    return Response(
                        {"error": f"Invalid bounds format: {e}"}, status=400
                    )

            # Apply limit (default 2000, max 5000)
            limit = min(int(request.query_params.get("limit", 2000)), 5000)
            queryset = queryset[:limit]

            # Build GeoJSON FeatureCollection
            features = []
            for body in queryset:
                pp = body.census_record.populated_place if body.census_record else None
                county = body.census_record.county if body.census_record else None
                if pp and pp.lat and pp.lon:
                    feature = {
                        "type": "Feature",
                        "geometry": {
                            "type": "Point",
                            "coordinates": [
                                float(pp.lon),
                                float(pp.lat),
                            ],
                        },
                        "properties": {
                            "id": body.id,
                            "congregation_name": body.name or "Unnamed",
                            "denomination": (
                                body.denomination.name
                                if body.denomination
                                else "Unknown"
                            ),
                            "denomination_id": (
                                body.denomination.id if body.denomination else None
                            ),
                            "family_census": (
                                body.denomination.family_census
                                if body.denomination
                                else None
                            ),
                            "family_relec": (
                                body.denomination.family_relec
                                if body.denomination
                                else None
                            ),
                            "address": body.address,
                            "populated_place": pp.name,
                            "city": pp.name,
                            "county": county.name if county else None,
                            "state": (
                                county.state.code
                                if county and county.state
                                else None
                            ),
                            "num_edifices": body.num_edifices,
                            "edifice_value": (
                                float(body.edifice_value)
                                if body.edifice_value
                                else None
                            ),
                            "schedule_id": (
                                body.census_record.schedule_id
                                if body.census_record
                                else None
                            ),
                            "transcription_status": (
                                body.census_record.transcription_status
                                if body.census_record
                                else None
                            ),
                        },
                    }
                    features.append(feature)

            geojson = {"type": "FeatureCollection", "features": features}

            return Response(geojson)

        except Exception as e:
            import traceback

            return Response(
                {"error": str(e), "traceback": traceback.format_exc()}, status=500
            )

    @action(detail=False, methods=["get"])
    def places_geojson(self, request):
        """
        GeoJSON endpoint aggregated by populated place.
        Returns one feature per unique location (populated place) with all congregations
        at that location grouped together.

        Each feature represents a populated place with:
        - Single point at the city/town lat/lon
        - Count of congregations at that location
        - Array of all congregations with their details
        - List of unique denominations present

        Query Parameters:
            - denomination: Specific denomination ID(s) - supports multiple
            - family_census: Filter by census denomination family
            - family_relec: Filter by RelEc denomination family
            - exclude_families: Comma-separated list of families to exclude
            - transcription_status: Only include schedules with this status (e.g., 'approved')
            - bounds: Optional bounding box as "south,west,north,east"
            - limit: Maximum number of locations to return (default: 500, use 99999 for all)
        """
        try:
            from collections import defaultdict

            # Start with base queryset - ReligiousBody with populated place coordinates
            queryset = ReligiousBody.objects.filter(
                census_record__populated_place__isnull=False,
                census_record__populated_place__lat__isnull=False,
                census_record__populated_place__lon__isnull=False,
            ).select_related(
                "census_record__populated_place__county__state",
                "census_record__county__state",
                "denomination",
            )

            # Filter by denomination family (census)
            if "family_census" in request.query_params:
                family_census = request.query_params.getlist("family_census")
                # Only filter if we have non-empty values
                if family_census and any(f for f in family_census if f):
                    queryset = queryset.filter(
                        denomination__family_census__in=family_census
                    )
            # Filter by denomination family (relec)
            if "family_relec" in request.query_params:
                family_relec = request.query_params.getlist("family_relec")
                # Only filter if we have non-empty values
                if family_relec and any(f for f in family_relec if f):
                    queryset = queryset.filter(
                        denomination__family_relec__in=family_relec
                    )

            # Exclude specific families (for filtering out major denominations)
            if "exclude_families" in request.query_params:
                exclude = request.query_params.get("exclude_families").split(",")
                queryset = queryset.exclude(denomination__family_census__in=exclude)

            # Filter by specific denomination(s) - supports multiple IDs
            if "denomination" in request.query_params:
                denomination_ids = request.query_params.getlist("denomination")
                # Only filter if we have non-empty values
                if denomination_ids and any(d for d in denomination_ids if d):
                    queryset = queryset.filter(denomination_id__in=denomination_ids)

            # Filter by transcription status (e.g., only show fully transcribed congregations)
            if "transcription_status" in request.query_params:
                status = request.query_params.get("transcription_status")
                if status:  # Only filter if status is not empty
                    queryset = queryset.filter(
                        census_record__transcription_status=status
                    )

            # Filter by urban/rural status (urban_rural_code is on ReligiousBody)
            if "urban_rural" in request.query_params:
                urban_rural = request.query_params.get("urban_rural")
                if urban_rural == "urban":
                    queryset = queryset.filter(urban_rural_code="Urban")
                elif urban_rural == "rural":
                    queryset = queryset.filter(urban_rural_code="Rural")

            # Apply bounding box filter if provided
            if "bounds" in request.query_params:
                bounds = request.query_params.get("bounds")
                try:
                    south, west, north, east = map(float, bounds.split(","))
                    queryset = queryset.filter(
                        census_record__populated_place__lat__gte=south,
                        census_record__populated_place__lat__lte=north,
                        census_record__populated_place__lon__gte=west,
                        census_record__populated_place__lon__lte=east,
                    )
                except (ValueError, TypeError) as e:
                    return Response(
                        {"error": f"Invalid bounds format: {e}"}, status=400
                    )

            # Group congregations by populated place
            places = defaultdict(list)
            for body in queryset:
                pp = body.census_record.populated_place if body.census_record else None
                if pp and pp.lat and pp.lon:
                    places[pp.id].append(body)

            # Apply limit to number of places (default: all locations)
            limit = int(request.query_params.get("limit", 99999))
            limited_places = (
                dict(list(places.items())[:limit]) if limit < 99999 else places
            )

            # Build GeoJSON FeatureCollection
            features = []
            for place_id, congregations in limited_places.items():
                if not congregations:
                    continue

                # Get populated place and county from first congregation
                pp = congregations[0].census_record.populated_place
                county = congregations[0].census_record.county

                # Collect unique denominations at this place
                denominations = set()
                congregation_details = []

                for body in congregations:
                    if body.denomination:
                        denominations.add(body.denomination.name)

                    congregation_details.append(
                        {
                            "id": body.id,
                            "name": body.name or "Unnamed",
                            "denomination": (
                                body.denomination.name
                                if body.denomination
                                else "Unknown"
                            ),
                            "denomination_id": (
                                body.denomination.id if body.denomination else None
                            ),
                            "family_census": (
                                body.denomination.family_census
                                if body.denomination
                                else None
                            ),
                            "family_relec": (
                                body.denomination.family_relec
                                if body.denomination
                                else None
                            ),
                            "address": body.address,
                            "num_edifices": body.num_edifices,
                            "edifice_value": (
                                float(body.edifice_value)
                                if body.edifice_value
                                else None
                            ),
                            "schedule_id": (
                                body.census_record.schedule_id
                                if body.census_record
                                else None
                            ),
                            "census_record_id": (
                                body.census_record.resource_id
                                if body.census_record
                                else None
                            ),
                            "transcription_status": (
                                body.census_record.transcription_status
                                if body.census_record
                                else None
                            ),
                        }
                    )

                feature = {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [float(pp.lon), float(pp.lat)],
                    },
                    "properties": {
                        "place_id": place_id,
                        "populated_place": pp.name,
                        "city": pp.name,
                        "county": county.name if county else None,
                        "state": (
                            county.state.code if county and county.state else None
                        ),
                        "congregation_count": len(congregations),
                        "denominations": sorted(list(denominations)),
                        "denominations_count": len(denominations),
                        "congregations": congregation_details,
                    },
                }
                features.append(feature)

            geojson = {"type": "FeatureCollection", "features": features}

            return Response(geojson)

        except Exception as e:
            import traceback

            return Response(
                {"error": str(e), "traceback": traceback.format_exc()}, status=500
            )

    @action(detail=False, methods=["get"])
    def city_membership(self, request):
        """
        Per-congregation membership endpoint with full demographic breakdown.

        Returns individual congregation records with their complete membership
        data as recorded in the census, along with location and denomination info.

        Query Parameters:
            - denomination: Filter by specific denomination name
            - denominationFamily: Filter by family_relec value
            - family_census: Filter by census denomination family
            - bounds: Bounding box as "south,west,north,east"
            - limit: Maximum number of records (default: 2000)

        Returns: Array of congregation objects with full membership breakdown
        """
        try:
            queryset = (
                ReligiousBody.objects.filter(
                    census_record__populated_place__isnull=False,
                    census_record__populated_place__lat__isnull=False,
                    census_record__populated_place__lon__isnull=False,
                )
                .select_related(
                    "census_record__populated_place",
                    "census_record__county__state",
                    "denomination",
                )
                .prefetch_related("membership")
            )

            # Filter by denomination family (relec)
            if "denominationFamily" in request.query_params:
                family = request.query_params.get("denominationFamily")
                queryset = queryset.filter(denomination__family_relec=family)

            # Filter by denomination family (census)
            if "family_census" in request.query_params:
                family_census = request.query_params.get("family_census")
                queryset = queryset.filter(
                    denomination__family_census=family_census
                )

            # Filter by denomination name
            if "denomination" in request.query_params:
                denom_name = request.query_params.get("denomination")
                queryset = queryset.filter(denomination__name=denom_name)

            # Bounds filtering
            if "bounds" in request.query_params:
                bounds = request.query_params.get("bounds")
                try:
                    south, west, north, east = map(float, bounds.split(","))
                    queryset = queryset.filter(
                        census_record__populated_place__lat__gte=south,
                        census_record__populated_place__lat__lte=north,
                        census_record__populated_place__lon__gte=west,
                        census_record__populated_place__lon__lte=east,
                    )
                except (ValueError, TypeError):
                    pass

            limit = min(int(request.query_params.get("limit", 2000)), 5000)
            queryset = queryset[:limit]

            response_data = []
            for body in queryset:
                pp = body.census_record.populated_place if body.census_record else None
                county = body.census_record.county if body.census_record else None
                membership = body.membership.first()

                record = {
                    "id": body.id,
                    "name": body.name,
                    "city": pp.name if pp else None,
                    "county": county.name if county else None,
                    "state": county.state.code if county and county.state else None,
                    "lat": float(pp.lat) if pp and pp.lat else None,
                    "lon": float(pp.lon) if pp and pp.lon else None,
                    "denomination": body.denomination.name if body.denomination else None,
                    "family_census": body.denomination.family_census if body.denomination else None,
                    "family_relec": body.denomination.family_relec if body.denomination else None,
                }

                if membership:
                    record["membership"] = {
                        "male_members": membership.male_members,
                        "female_members": membership.female_members,
                        "total_members_by_sex": membership.total_members_by_sex,
                        "members_under_13": membership.members_under_13,
                        "members_13_and_older": membership.members_13_and_older,
                        "total_members_by_age": membership.total_members_by_age,
                        "sunday_school_num_officers_teachers": membership.sunday_school_num_officers_teachers,
                        "sunday_school_num_scholars": membership.sunday_school_num_scholars,
                        "vbs_num_officers_teachers": membership.vbs_num_officers_teachers,
                        "vbs_num_scholars": membership.vbs_num_scholars,
                        "weekday_num_officers_teachers": membership.weekday_num_officers_teachers,
                        "weekday_num_scholars": membership.weekday_num_scholars,
                        "parochial_num_administrators": membership.parochial_num_administrators,
                        "parochial_num_elementary_teachers": membership.parochial_num_elementary_teachers,
                        "parochial_num_secondary_teachers": membership.parochial_num_secondary_teachers,
                        "parochial_num_elementary_scholars": membership.parochial_num_elementary_scholars,
                        "parochial_num_secondary_scholars": membership.parochial_num_secondary_scholars,
                    }
                else:
                    record["membership"] = None

                response_data.append(record)

            return Response(response_data)

        except Exception as e:
            import traceback

            return Response(
                {"error": str(e), "traceback": traceback.format_exc()}, status=500
            )

    @action(detail=False, methods=["get"])
    def denomination_families(self, request):
        """
        List unique denomination families endpoint.
        Matches the external data.chnm.org/relcensus/city-membership API structure.

        Returns both census families and RelEc families, with counts of denominations
        and congregations in each family.

        Returns: Object with census_families and relec_families arrays
        """
        try:
            from django.db.models import Count

            # Get all unique census families with counts
            census_families_data = []

            # Get all families (not just those with location data)
            census_families = (
                Denomination.objects.filter(family_census__isnull=False)
                .values("family_census")
                .annotate(
                    denomination_count=Count("id", distinct=True),
                    total_congregation_count=Count("religiousbody", distinct=True),
                )
                .order_by("family_census")
            )

            # For each family, get count of congregations WITH location data
            for family in census_families:
                if family["family_census"]:  # Skip null/empty
                    family_name = family["family_census"]

                    # Count congregations with location data
                    congregation_count_with_location = (
                        Denomination.objects.filter(
                            family_census=family_name,
                            religiousbody__census_record__populated_place__isnull=False,
                        )
                        .values("religiousbody")
                        .distinct()
                        .count()
                    )

                    census_families_data.append(
                        {
                            "name": family_name,
                            "denominations": family["denomination_count"],
                            "congregations": congregation_count_with_location,
                            "total_congregations": family["total_congregation_count"],
                            "has_location_data": congregation_count_with_location > 0,
                        }
                    )

            # Get all unique RelEc families with counts
            relec_families_data = []

            # Get all families (not just those with location data)
            relec_families = (
                Denomination.objects.filter(family_relec__isnull=False)
                .values("family_relec")
                .annotate(
                    denomination_count=Count("id", distinct=True),
                    total_congregation_count=Count("religiousbody", distinct=True),
                )
                .order_by("family_relec")
            )

            # For each family, get count of congregations WITH location data
            for family in relec_families:
                if family["family_relec"]:  # Skip null/empty
                    family_name = family["family_relec"]

                    # Count congregations with location data
                    congregation_count_with_location = (
                        Denomination.objects.filter(
                            family_relec=family_name,
                            religiousbody__census_record__populated_place__isnull=False,
                        )
                        .values("religiousbody")
                        .distinct()
                        .count()
                    )

                    relec_families_data.append(
                        {
                            "name": family_name,
                            "denominations": family["denomination_count"],
                            "congregations": congregation_count_with_location,
                            "total_congregations": family["total_congregation_count"],
                            "has_location_data": congregation_count_with_location > 0,
                        }
                    )

            return Response(
                {
                    "census_families": census_families_data,
                    "relec_families": relec_families_data,
                }
            )

        except Exception as e:
            import traceback

            return Response(
                {"error": str(e), "traceback": traceback.format_exc()}, status=500
            )

    @action(detail=False, methods=["get"])
    def hugo_city_membership(self, request):
        """Proxy endpoint for Hugo API city membership data to avoid CORS issues"""
        try:
            # Build the external API URL with query parameters
            external_url = "https://data.chnm.org/relcensus/city-membership"

            # Forward all query parameters - convert MultiValueDict to regular dict
            # MultiValueDict stores lists, we need single values
            params = {key: value for key, value in request.query_params.items()}

            # Make request to external API
            response = requests.get(external_url, params=params, timeout=30)
            response.raise_for_status()

            # Return the JSON data
            return Response(response.json())

        except requests.exceptions.RequestException as e:
            return Response(
                {"error": f"Failed to fetch data from external API: {str(e)}"},
                status=502,
            )
        except Exception as e:
            import traceback

            return Response(
                {"error": str(e), "traceback": traceback.format_exc()}, status=500
            )
