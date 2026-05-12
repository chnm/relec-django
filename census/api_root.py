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
                "version": "2.0",
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
                    "by_family": f"{base_url}denominations/by_family/?family_census=Adventist+bodies",
                    "description": "Denomination taxonomy and family classifications",
                    "filters": ["family_census", "family_relec", "search"],
                },
                "religious_bodies": {
                    "list": f"{base_url}religious-bodies/?limit=10",
                    "detail": f"{base_url}religious-bodies/{{id}}/",
                    "description": "Individual congregation records with location, denomination, membership, finances, pastors, and transcription status",
                    "filters": [
                        "denomination (integer, denomination ID)",
                        "family_census (string, census family name)",
                        "family_relec (string, RelEc family name)",
                        "transcription_status (string, e.g. 'approved')",
                        "exclude_families (comma-separated census families to exclude)",
                        "urban_rural (string, 'urban' or 'rural')",
                        "bounds (string, 'south,west,north,east' bounding box)",
                        "search (string, name/address/census code)",
                    ],
                    "examples": {
                        "by_family": f"{base_url}religious-bodies/?family_relec=Adventist&limit=5",
                        "approved_only": f"{base_url}religious-bodies/?transcription_status=approved&limit=10",
                        "bounding_box": f"{base_url}religious-bodies/?bounds=38,-78,40,-75&limit=100",
                        "urban_only": f"{base_url}religious-bodies/?urban_rural=urban&limit=10",
                    },
                    "response_notes": {
                        "denominations": "Array of denomination names matched by the current query filters, included alongside pagination metadata",
                        "location_details": "Nested object with lat, lon, city_name, county_name, state_name, place_id, address, urban_rural_code",
                        "membership_details": "Full membership breakdown including education program data; null values indicate blank fields (not zero)",
                        "finances": "Financial data (expenditures, benevolences, edifice/residence values and debts)",
                        "pastors": "Array of clergy objects (principal pastor first, then assistants) with name, is_assistant, college, theological_seminary, num_other_churches_served, serving_congregation",
                        "num_assistant_pastors": "Raw count of assistant pastors from form field 26 (integer or null)",
                        "respondent": "Person who signed the form: name, title, po_address, date_signed (null if no data)",
                        "processing": "Census Bureau intake metadata: date_received (ISO date), district_stamp, denomination_code_stamp (null if no data)",
                        "marginalia": "Array of {page_location, marginalia_transcription} for handwritten marks on the form (null if none)",
                        "ai_notes": "Free-form observations from the AI transcriber about anomalies or illegibility (null if none)",
                        "transcription_status": "Status of the census record transcription",
                        "schedule_id": "Census schedule identifier",
                        "urls.image": "Direct URL to the original census schedule image in object storage (null if not yet fetched)",
                    },
                },
                "denomination_families": {
                    "url": f"{base_url}religious-bodies/denomination_families/",
                    "description": "List of denomination families with counts",
                    "returns": "Census families and RelEc families with denomination/congregation counts",
                },
            },
            "usage_tips": [
                "Always use filters to limit results",
                "Add ?limit=10 to test queries before running full requests",
                "Use bounds filter for geographic queries",
                "Use transcription_status=approved for verified data only",
            ],
        }
    )
