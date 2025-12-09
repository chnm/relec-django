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
    DemographicsMapSerializer,
    DenominationSerializer,
    MapMarkerSerializer,
    ReligiousBodySerializer,
)


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
        # religiousbody is the default reverse relation name (lowercase model name)
        census_families = (
            Denomination.objects.filter(
                religiousbody__location__isnull=False,
                religiousbody__location__lat__isnull=False,
                religiousbody__location__lon__isnull=False,
            )
            .values_list("family_census", flat=True)
            .distinct()
            .order_by("family_census")
        )

        relec_families = (
            Denomination.objects.filter(
                religiousbody__location__isnull=False,
                religiousbody__location__lat__isnull=False,
                religiousbody__location__lon__isnull=False,
            )
            .values_list("family_relec", flat=True)
            .distinct()
            .order_by("family_relec")
        )

        # Count denominations in each family that have location data
        family_counts = {}
        for family in census_families:
            if family:  # Skip empty family names
                count = (
                    Denomination.objects.filter(
                        family_census=family,
                        religiousbody__location__isnull=False,
                        religiousbody__location__lat__isnull=False,
                        religiousbody__location__lon__isnull=False,
                    )
                    .distinct()
                    .count()
                )
                family_counts[family] = count

        return Response(
            {
                "census_families": [
                    {"name": family, "count": family_counts.get(family, 0)}
                    for family in census_families
                    if family
                ],
                "relec_families": list(relec_families),
            }
        )

    @action(detail=False, methods=["get"])
    def by_family(self, request):
        """Return denominations grouped by family - only those with location data"""
        family = request.query_params.get("family_census", None)

        # Base filter for location data - use religiousbody (the default reverse relation)
        location_filter = {
            "religiousbody__location__isnull": False,
            "religiousbody__location__lat__isnull": False,
            "religiousbody__location__lon__isnull": False,
        }

        if family:
            denominations = (
                Denomination.objects.filter(family_census=family, **location_filter)
                .distinct()
                .order_by("name")
            )
        else:
            denominations = (
                Denomination.objects.filter(**location_filter)
                .distinct()
                .order_by("family_census", "name")
            )

        serializer = self.get_serializer(denominations, many=True)
        return Response(serializer.data)


class ReligiousBodyViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ReligiousBody.objects.all().select_related(
        "location", "denomination", "census_record"
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

    @action(detail=False, methods=["get"])
    def demographics_data(self, request):
        """Enhanced geodata endpoint for demographics map display with membership data"""
        try:
            # Start with base queryset - only select what we need for demographics
            queryset = (
                ReligiousBody.objects.filter(location__isnull=False)
                .select_related("location", "denomination")
                .prefetch_related("membership")
            )

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

            # Use the demographics serializer
            serializer = DemographicsMapSerializer(queryset, many=True)
            data = serializer.data

            print(f"Returning {len(data)} demographics map markers")
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
                location__isnull=False,
                location__lat__isnull=False,
                location__lon__isnull=False,
            ).select_related("location", "denomination", "census_record")

            # Filter by denomination family (census)
            if "family_census" in request.query_params:
                family_census = request.query_params.getlist("family_census")
                # Only filter if we have non-empty values
                if family_census and any(f for f in family_census if f):
                    queryset = queryset.filter(
                        denomination__family_census__in=family_census
                    )
            else:
                # Default: when no family is specified, only show families that have location data
                # This matches what appears in the family dropdown
                available_families = (
                    Denomination.objects.filter(
                        religiousbody__location__isnull=False,
                        religiousbody__location__lat__isnull=False,
                        religiousbody__location__lon__isnull=False,
                    )
                    .values_list("family_census", flat=True)
                    .distinct()
                )
                queryset = queryset.filter(
                    denomination__family_census__in=available_families
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
                        location__lat__gte=south,
                        location__lat__lte=north,
                        location__lon__gte=west,
                        location__lon__lte=east,
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
                if body.location and body.location.lat and body.location.lon:
                    feature = {
                        "type": "Feature",
                        "geometry": {
                            "type": "Point",
                            "coordinates": [
                                float(body.location.lon),
                                float(body.location.lat),
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
                            "populated_place": (
                                body.location.map_name or body.location.city
                                if body.location
                                else None
                            ),
                            "city": body.location.city if body.location else None,
                            "county": body.location.county if body.location else None,
                            "state": body.location.state if body.location else None,
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
                location__isnull=False,
                location__lat__isnull=False,
                location__lon__isnull=False,
            ).select_related("location", "denomination", "census_record")

            # Filter by denomination family (census)
            if "family_census" in request.query_params:
                family_census = request.query_params.getlist("family_census")
                # Only filter if we have non-empty values
                if family_census and any(f for f in family_census if f):
                    queryset = queryset.filter(
                        denomination__family_census__in=family_census
                    )
            else:
                # Default: when no family is specified, only show families that have location data
                # This matches what appears in the family dropdown
                available_families = (
                    Denomination.objects.filter(
                        religiousbody__location__isnull=False,
                        religiousbody__location__lat__isnull=False,
                        religiousbody__location__lon__isnull=False,
                    )
                    .values_list("family_census", flat=True)
                    .distinct()
                )
                queryset = queryset.filter(
                    denomination__family_census__in=available_families
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
                        location__lat__gte=south,
                        location__lat__lte=north,
                        location__lon__gte=west,
                        location__lon__lte=east,
                    )
                except (ValueError, TypeError) as e:
                    return Response(
                        {"error": f"Invalid bounds format: {e}"}, status=400
                    )

            # Group congregations by location
            places = defaultdict(list)
            for body in queryset:
                if body.location and body.location.lat and body.location.lon:
                    # Use location ID as the key to group
                    location_key = body.location.id
                    places[location_key].append(body)

            # Apply limit to number of places (default 500, no max for "All")
            limit = int(request.query_params.get("limit", 500))
            limited_places = (
                dict(list(places.items())[:limit]) if limit < 99999 else places
            )

            # Build GeoJSON FeatureCollection
            features = []
            for location_id, congregations in limited_places.items():
                if not congregations:
                    continue

                # Get location from first congregation
                location = congregations[0].location

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
                        "coordinates": [float(location.lon), float(location.lat)],
                    },
                    "properties": {
                        "location_id": location.id,
                        "populated_place": location.map_name or location.city,
                        "city": location.city,
                        "county": location.county,
                        "state": location.state,
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
