from django.core.cache import cache
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, render
from django.views.decorators.cache import cache_page

from location.models import County, State
from .models import CensusSchedule, Denomination


def _get_census_browser_filter_data():
    """Cache the expensive dropdown/filter data used by the census browser.

    This data (all denominations, counties by state, places by county,
    denomination families) is the same for every request and is the most
    expensive part of the census browser view.
    """
    cache_key = "census_browser_filter_data"
    data = cache.get(cache_key)
    if data is not None:
        return data

    import json

    denominations = list(Denomination.objects.all().order_by("name"))
    census_families = list(
        Denomination.objects.values_list("family_relec", flat=True)
        .distinct()
        .order_by("family_relec")
    )

    states = list(State.objects.all().order_by("name"))

    # Counties grouped by state
    counties_by_state = {}
    county_data = (
        County.objects.select_related("state")
        .values("state__code", "name")
        .order_by("state__code", "name")
    )
    for item in county_data:
        state = item["state__code"]
        county = item["name"]
        if state not in counties_by_state:
            counties_by_state[state] = []
        counties_by_state[state].append(county)

    # Populated places grouped by state+county
    places_by_county = {}
    place_data = (
        CensusSchedule.objects.filter(
            populated_place__isnull=False, county__isnull=False
        )
        .values("county__state__code", "county__name", "populated_place__name")
        .distinct()
        .order_by("county__state__code", "county__name", "populated_place__name")
    )
    for item in place_data:
        state = item["county__state__code"]
        county = item["county__name"]
        place = item["populated_place__name"]
        if state not in places_by_county:
            places_by_county[state] = {}
        if county not in places_by_county[state]:
            places_by_county[state][county] = []
        places_by_county[state][county].append(place)

    # Denominations grouped by family
    denominations_by_family = {}
    for denom in denominations:
        family = denom.family_relec if denom.family_relec else "Other"
        if family not in denominations_by_family:
            denominations_by_family[family] = []
        denominations_by_family[family].append({"id": denom.id, "name": denom.name})

    data = {
        "denominations": denominations,
        "census_families": census_families,
        "states": states,
        "counties_by_state_json": json.dumps(counties_by_state),
        "places_by_county_json": json.dumps(places_by_county),
        "denominations_by_family_json": json.dumps(denominations_by_family),
    }

    cache.set(cache_key, data, 60 * 30)  # Cache for 30 minutes
    return data



@cache_page(60 * 10)  # 10 minutes
def census_browser_view(request, state_code=None, county_name=None):
    """Render the census records browser with filtering and pagination"""
    from urllib.parse import unquote

    # Get filter parameters - path params take precedence over query params
    search = request.GET.get("search", "")
    denomination_filter = request.GET.get("denomination", "")
    family_filter = request.GET.get("family", "")
    family_census_filter = request.GET.get("family_census", "")
    # Support both path parameters and legacy query parameters
    state_filter = state_code or request.GET.get("location", "")
    county_filter = (
        unquote(county_name) if county_name else request.GET.get("county", "")
    )
    place_filter = request.GET.get("place", "")
    has_membership = request.GET.get("has_membership", "")
    urban_rural = request.GET.get("urban_rural", "")

    # Base queryset with related data (using new location hierarchy)
    queryset = (
        CensusSchedule.objects.select_related(
            "county",
            "county__state",
            "populated_place",
            "schedule_denomination",
        )
        .prefetch_related(
            "church_details__denomination",
            "membership_details",
            "clergy",
        )
        .order_by("schedule_denomination")
    )

    # Apply filters
    if search:
        queryset = queryset.filter(
            Q(schedule_title__icontains=search)
            | Q(church_details__name__icontains=search)
            | Q(church_details__denomination__name__icontains=search)
            | Q(schedule_denomination__name__icontains=search)
            | Q(notes__icontains=search)
            | Q(county__name__icontains=search)
            | Q(populated_place__name__icontains=search)
        )

    if denomination_filter:
        # Check both schedule-level and religious body level denomination
        queryset = queryset.filter(
            Q(schedule_denomination_id=denomination_filter)
            | Q(church_details__denomination_id=denomination_filter)
        )

    if family_filter:
        queryset = queryset.filter(
            Q(schedule_denomination__family_relec=family_filter)
            | Q(church_details__denomination__family_relec=family_filter)
        )

    if family_census_filter:
        queryset = queryset.filter(
            Q(schedule_denomination__family_census=family_census_filter)
            | Q(church_details__denomination__family_census=family_census_filter)
        )

    if state_filter:
        queryset = queryset.filter(county__state__code=state_filter)

    if county_filter:
        queryset = queryset.filter(county__name__icontains=county_filter)

    if place_filter:
        queryset = queryset.filter(populated_place__name__iexact=place_filter)

    if has_membership == "yes":
        queryset = queryset.filter(membership_details__isnull=False).distinct()
    elif has_membership == "no":
        queryset = queryset.filter(membership_details__isnull=True)

    if urban_rural == "urban":
        queryset = queryset.filter(church_details__urban_rural_code="Urban")
    elif urban_rural == "rural":
        queryset = queryset.filter(church_details__urban_rural_code="Rural")

    # Pagination
    paginator = Paginator(queryset.distinct(), 20)  # Show 20 records per page
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    # Get cached filter/dropdown data (most expensive part of this view)
    filter_data = _get_census_browser_filter_data()

    # Get current state object for display
    current_state = None
    if state_filter:
        current_state = State.objects.filter(code=state_filter).first()

    context = {
        "page_obj": page_obj,
        **filter_data,
        "search": search,
        "denomination_filter": denomination_filter,
        "family_filter": family_filter,
        "location_filter": state_filter,
        "county_filter": county_filter,
        "place_filter": place_filter,
        "current_state": current_state,
        "has_membership": has_membership,
        "urban_rural": urban_rural,
        "total_records": paginator.count,
    }

    return render(request, "census/browser.html", context)


@cache_page(60 * 15)  # 15 minutes
def census_detail_view(request, resource_id):
    """Render detailed view of a single census record"""

    census_record = get_object_or_404(
        CensusSchedule.objects.select_related(
            "county",
            "county__state",
            "populated_place",
            "populated_place__county",
            "schedule_denomination",
        ).prefetch_related(
            "church_details__denomination",
            "membership_details",
            "clergy",
        ),
        resource_id=resource_id,
    )

    context = {
        "census_record": census_record,
    }

    return render(request, "census/detail.html", context)


@cache_page(60 * 15)  # 15 minutes
def denominations_browse_view(request):
    """Browse denominations with counts and links to filtered census records"""

    denominations_with_counts = (
        Denomination.objects.annotate(
            schedule_count=Count("religiousbody__census_record")
        )
        .filter(schedule_count__gt=0)
        .order_by("name")
    )

    # Get family groupings
    families = {}
    for denomination in denominations_with_counts:
        family = denomination.family_relec or "Other"
        if family not in families:
            families[family] = []
        families[family].append(denomination)

    # Sort families by name, but put "Other" last
    sorted_families = sorted(
        families.items(), key=lambda x: ("ZZZ" if x[0] == "Other" else x[0])
    )

    context = {
        "families": sorted_families,
        "total_denominations": denominations_with_counts.count(),
    }

    return render(request, "census/denominations_browse.html", context)


@cache_page(60 * 15)  # 15 minutes
def locations_browse_view(request):
    """Browse locations (states and counties) with counts"""

    # Get state-level counts using new location hierarchy
    states_with_counts = (
        CensusSchedule.objects.filter(county__isnull=False)
        .values("county__state__code", "county__state__name")
        .annotate(schedule_count=Count("id"))
        .filter(schedule_count__gt=0)
        .order_by("county__state__name")
    )

    # Get county-level counts for each state
    counties_with_counts = (
        CensusSchedule.objects.filter(county__isnull=False)
        .values("county__state__code", "county__name")
        .annotate(schedule_count=Count("id"))
        .filter(schedule_count__gt=0)
        .order_by("county__state__code", "county__name")
    )

    # Group counties by state
    states_data = {}
    for state in states_with_counts:
        state_code = state["county__state__code"]
        state_name = state["county__state__name"]
        states_data[state_code] = {
            "name": state_name,
            "total_count": state["schedule_count"],
            "counties": [],
        }

    for county in counties_with_counts:
        state_code = county["county__state__code"]
        if state_code in states_data:
            states_data[state_code]["counties"].append(
                {"name": county["county__name"], "count": county["schedule_count"]}
            )

    # Calculate total counties across all states
    total_counties = sum(len(state["counties"]) for state in states_data.values())

    # Count distinct populated places that have schedules
    from location.models import PopulatedPlace

    total_populated_places = PopulatedPlace.objects.filter(
        census_schedules__isnull=False
    ).distinct().count()

    context = {
        "states_data": states_data,
        "total_states": len(states_data),
        "total_counties": total_counties,
        "total_populated_places": total_populated_places,
    }

    return render(request, "census/locations_browse.html", context)


@cache_page(60 * 15)  # 15 minutes
def populated_places_browse_view(request):
    """Browse populated places organized by state and county with counts"""
    from location.models import PopulatedPlace

    # Get all populated places with schedules, grouped by state and county
    places_with_counts = (
        CensusSchedule.objects.filter(
            populated_place__isnull=False, county__isnull=False
        )
        .values(
            "county__state__code",
            "county__state__name",
            "county__name",
            "populated_place__name",
            "populated_place__id",
        )
        .annotate(schedule_count=Count("id"))
        .filter(schedule_count__gt=0)
        .order_by("county__state__name", "county__name", "populated_place__name")
    )

    # Build hierarchical structure: State -> County -> Places
    states_data = {}
    for item in places_with_counts:
        state_code = item["county__state__code"]
        state_name = item["county__state__name"]
        county_name = item["county__name"]
        place_name = item["populated_place__name"]
        place_id = item["populated_place__id"]
        count = item["schedule_count"]

        # Initialize state if not exists
        if state_code not in states_data:
            states_data[state_code] = {
                "name": state_name,
                "total_count": 0,
                "counties": {},
            }

        # Initialize county if not exists
        if county_name not in states_data[state_code]["counties"]:
            states_data[state_code]["counties"][county_name] = {
                "name": county_name,
                "total_count": 0,
                "places": [],
            }

        # Add place to county
        states_data[state_code]["counties"][county_name]["places"].append(
            {"name": place_name, "id": place_id, "count": count}
        )

        # Update counts
        states_data[state_code]["counties"][county_name]["total_count"] += count
        states_data[state_code]["total_count"] += count

    # Convert counties dict to list for easier template iteration
    for state_code in states_data:
        counties_dict = states_data[state_code]["counties"]
        states_data[state_code]["counties"] = [
            {
                "name": county_name,
                "total_count": data["total_count"],
                "places": data["places"],
            }
            for county_name, data in sorted(counties_dict.items())
        ]

    # Calculate totals
    total_states = len(states_data)
    total_counties = sum(
        len(state["counties"]) for state in states_data.values()
    )
    total_places = PopulatedPlace.objects.filter(
        census_schedules__isnull=False
    ).distinct().count()

    context = {
        "states_data": states_data,
        "total_states": total_states,
        "total_counties": total_counties,
        "total_places": total_places,
    }

    return render(request, "census/populated_places_browse.html", context)



@cache_page(60 * 15)  # 15 minutes
def api_documentation_view(request):
    """
    API Documentation page for the Religious Ecologies Census Data API.

    Provides comprehensive documentation for internal and external users
    who want to access the 1926 Census of Religious Bodies data.
    """
    context = {
        "api_base_url": request.build_absolute_uri("/census/api/"),
    }

    return render(request, "census/api_documentation.html", context)
