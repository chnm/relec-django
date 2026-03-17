"""
Custom API views for the census app.
Includes custom API root with detailed endpoint documentation.
"""

from django.views.decorators.cache import cache_page
from rest_framework.decorators import api_view
from rest_framework.response import Response


@cache_page(60 * 60)
@api_view(["GET"])
def api_root(request, format=None):
    """
    Religious Ecologies API Root

    This API provides access to 1926 U.S. Census of Religious Bodies data.
    All endpoints return JSON. Most endpoints support filtering via query parameters.
    """
    # Build base URL from request
    base_url = request.build_absolute_uri("/census/api/")

    return Response(
        {
            "info": {
                "version": "1.0",
                "description": "Religious Ecologies Census Data API",
                "year": "1926",
                "total_denominations": "200+",
                "total_congregations": "3000+",
            },
            "endpoints": {
                "denominations": {
                    "list": f"{base_url}denominations/",
                    "detail": f"{base_url}denominations/{{id}}/",
                    "families": f"{base_url}denominations/families/",
                    "by_family": f"{base_url}denominations/by_family/?family_census=Baptist+bodies",
                    "description": "Denomination taxonomy and family classifications",
                    "filters": ["family_census", "family_relec", "search"],
                },
                "religious_bodies": {
                    "note": "⚠️  Use specialized endpoints below instead of /religious-bodies/ list to avoid large responses",
                    "list": f"{base_url}religious-bodies/?limit=10",
                    "detail": f"{base_url}religious-bodies/{{id}}/",
                    "description": "Individual congregation records (use filtered endpoints below)",
                    "recommended_endpoints": "See map_data, city_membership, geojson below",
                },
                "map_data": {
                    "url": f"{base_url}religious-bodies/map_data/",
                    "description": "Lightweight endpoint optimized for map markers",
                    "example": f"{base_url}religious-bodies/map_data/?family_census=Baptist+bodies",
                    "filters": [
                        "family_census",
                        "denomination",
                        "bounds (south,west,north,east)",
                        "limit (default: 5000, max: 5000)",
                    ],
                },
                "demographics_data": {
                    "url": f"{base_url}religious-bodies/demographics_data/",
                    "description": "Extended membership and demographics data for maps",
                    "filters": [
                        "family_census",
                        "denomination",
                        "bounds",
                        "transcription_status (default: approved)",
                        "limit (default: 5000, max: 5000)",
                    ],
                },
                "city_membership": {
                    "url": f"{base_url}religious-bodies/city_membership/",
                    "description": "Per-congregation membership with full demographic breakdown",
                    "example": f"{base_url}religious-bodies/city_membership/?denominationFamily=Baptist&limit=10",
                    "filters": [
                        "denomination (exact name)",
                        "denominationFamily",
                        "family_census",
                        "bounds (south,west,north,east)",
                        "limit (default: 2000, max: 5000)",
                    ],
                    "returns": "Array of congregations with complete membership records",
                },
                "denomination_families": {
                    "url": f"{base_url}religious-bodies/denomination_families/",
                    "description": "List of denomination families with counts",
                    "returns": "Census families and RelEc families with denomination/congregation counts",
                },
                "geojson": {
                    "url": f"{base_url}religious-bodies/geojson/",
                    "description": "GeoJSON FeatureCollection of congregations",
                    "example": f"{base_url}religious-bodies/geojson/?family_census=Methodist+bodies&limit=500",
                    "filters": [
                        "denomination",
                        "family_census",
                        "family_relec",
                        "exclude_families",
                        "transcription_status",
                        "bounds",
                        "limit (default: 2000, max: 5000)",
                    ],
                    "format": "GeoJSON Point features with congregation properties",
                },
                "places_geojson": {
                    "url": f"{base_url}religious-bodies/places_geojson/",
                    "description": "GeoJSON FeatureCollection aggregated by populated place",
                    "example": f"{base_url}religious-bodies/places_geojson/?limit=100",
                    "filters": [
                        "denomination",
                        "family_census",
                        "transcription_status",
                        "bounds",
                        "limit (default: 500)",
                    ],
                    "format": "GeoJSON with one feature per city containing all congregations",
                },
            },
            "usage_tips": [
                "Always use filters to limit results",
                "Use map_data/ or city_membership/ instead of the raw religious-bodies/ list",
                "Add ?limit=10 to test queries before running full requests",
                "GeoJSON endpoints are optimized for mapping applications",
                "City membership endpoint aggregates data by location",
            ],
            "external_documentation": f"{base_url}schema/",
        }
    )
