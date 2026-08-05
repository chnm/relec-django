"""
Custom API views for the census app.
Includes custom API root with detailed endpoint documentation.
"""

from django.views.decorators.cache import cache_page
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Denomination, ReligiousBody


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
                "total_denominations": Denomination.objects.count(),
                "total_congregations": ReligiousBody.objects.count(),
            },
            "endpoints": {
                "denominations": {
                    "list": f"{base_url}denominations/",
                    "detail": f"{base_url}denominations/{{id}}/",
                    "families": f"{base_url}denominations/families/",
                    "by_family": f"{base_url}denominations/by_family/?family_relec=Adventist",
                    "description": "Denomination taxonomy and family classifications",
                    "filters": ["family_census", "family_relec", "search", "page"],
                },
                "religious_bodies": {
                    "list": f"{base_url}religious-bodies/?page_size=10",
                    "detail": f"{base_url}religious-bodies/{{id}}/",
                    "description": "Individual congregation records with location, denomination, membership, finances, pastors, and candidate transcription runs",
                    "filters": [
                        "denomination (integer, denomination ID)",
                        "family_census (string, census family name)",
                        "family_relec (string, RelEc family name)",
                        "transcription_status (string, e.g. 'approved')",
                        "exclude_families (comma-separated census families to exclude)",
                        "urban_rural (string, 'urban' or 'rural')",
                        "bounds (string, 'south,west,north,east' bounding box)",
                        "has_location (boolean)",
                        "search (string, name/address/census code)",
                        "page (integer, default page size 100)",
                        "page_size (integer, maximum 5000)",
                        "ordering ('name' or 'census_record__schedule_id'; prefix '-' for descending)",
                        "view ('map' for a reduced high-volume response)",
                    ],
                    "examples": {
                        "by_family": f"{base_url}religious-bodies/?family_relec=Adventist&page_size=5",
                        "approved_only": f"{base_url}religious-bodies/?transcription_status=approved&page_size=10",
                        "bounding_box": f"{base_url}religious-bodies/?bounds=38,-78,40,-75&page_size=100",
                        "urban_only": f"{base_url}religious-bodies/?urban_rural=urban&page_size=10",
                        "map_data": f"{base_url}religious-bodies/?page_size=5000&view=map",
                    },
                    "response_notes": {
                        "denominations": "Array of denomination names matched by the current query filters, included alongside pagination metadata",
                        "location_details": "Nested object with lat, lon, city_name, map_name, place_id, county_ahcb, county_name, state_name, address, urban_rural_code",
                        "membership_details": "Full membership breakdown including education program data; null values indicate blank fields (not zero)",
                        "finances": "Financial data (expenditures, benevolences, edifice/residence values and debts)",
                        "pastors": "Array of clergy objects (principal pastor first, then assistants) with name, is_assistant, college, theological_seminary, num_other_churches_served, serving_congregation",
                        "num_assistant_pastors": "Raw count of assistant pastors from form field 26 (integer or null)",
                        "respondent": "Person who signed the form: name, title, po_address, date_signed (null if no data)",
                        "processing": "Census Bureau intake metadata: date_received (ISO date), district_stamp, denomination_code_stamp (null if no data)",
                        "marginalia": "Array of {page_location, marginalia_transcription} for handwritten marks on the form (null if none)",
                        "transcriptions": "Array of immutable candidate outputs with a run key, kind, and raw JSON data; agent notes are stored inside data",
                        "schedule_id": "Census schedule identifier",
                        "urls.image": "Direct URL to the original census schedule image in object storage (null if not yet fetched)",
                        "view=map": "Omits transcriptions, pastors, num_assistant_pastors, respondent, processing, and marginalia",
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
                "Add ?page_size=10 to test queries before running full requests",
                "Use bounds filter for geographic queries",
                "Use transcription_status=approved for verified data only",
            ],
        }
    )
