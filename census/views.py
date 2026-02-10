from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, render

from location.models import County, State

from .models import CensusSchedule, Denomination


def map_view(request):
    """Render the map view with denomination filters"""
    # Get all denominations for the filter dropdown
    denominations = Denomination.objects.all().order_by("name")

    # Get unique denomination families for the family filter dropdown
    census_families = (
        Denomination.objects.values_list("family_census", flat=True)
        .distinct()
        .order_by("family_census")
    )
    relec_families = (
        Denomination.objects.values_list("family_relec", flat=True)
        .distinct()
        .order_by("family_relec")
    )

    context = {
        "denominations": denominations,
        "census_families": census_families,
        "relec_families": relec_families,
    }

    return render(request, "census/map.html", context)


def demographics_map_view(request):
    """Render the demographics map view with demographic filters"""
    # Get all denominations for the filter dropdown
    denominations = Denomination.objects.all().order_by("name")

    # Get unique denomination families for the family filter dropdown
    census_families = (
        Denomination.objects.values_list("family_census", flat=True)
        .distinct()
        .order_by("family_census")
    )
    relec_families = (
        Denomination.objects.values_list("family_relec", flat=True)
        .distinct()
        .order_by("family_relec")
    )

    context = {
        "denominations": denominations,
        "census_families": census_families,
        "relec_families": relec_families,
    }

    return render(request, "census/demographics_map.html", context)


def denomination_geojson_map_view(request):
    """Render the GeoJSON map test view for denominations by populated place"""
    return render(request, "census/denomination_geojson_map.html")


def census_browser_view(request, state_code=None, county_name=None):
    """Render the census records browser with filtering and pagination"""
    import json
    from urllib.parse import unquote

    # Get filter parameters - path params take precedence over query params
    search = request.GET.get("search", "")
    denomination_filter = request.GET.get("denomination", "")
    family_filter = request.GET.get("family", "")
    # Support both path parameters and legacy query parameters
    state_filter = state_code or request.GET.get("location", "")
    county_filter = (
        unquote(county_name) if county_name else request.GET.get("county", "")
    )
    has_image = request.GET.get("has_image", "")

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
            Q(schedule_denomination__family_census=family_filter)
            | Q(church_details__denomination__family_census=family_filter)
        )

    if state_filter:
        queryset = queryset.filter(county__state__code=state_filter)

    if county_filter:
        queryset = queryset.filter(county__name__icontains=county_filter)

    if has_image == "yes":
        queryset = queryset.exclude(original_image__isnull=True).exclude(
            original_image=""
        )
    elif has_image == "no":
        queryset = queryset.filter(
            Q(original_image__isnull=True) | Q(original_image="")
        )

    # Pagination
    paginator = Paginator(queryset.distinct(), 20)  # Show 20 records per page
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    # Get filter options
    denominations = Denomination.objects.all().order_by("name")
    census_families = (
        Denomination.objects.values_list("family_census", flat=True)
        .distinct()
        .order_by("family_census")
    )

    # Get states for location dropdown (from new State model)
    states = State.objects.all().order_by("name")

    # Get counties grouped by state for JavaScript (from new County model)
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

    # Get denominations grouped by family for JavaScript
    denominations_by_family = {}
    for denom in denominations:
        family = denom.family_census if denom.family_census else "Other"
        if family not in denominations_by_family:
            denominations_by_family[family] = []
        denominations_by_family[family].append({"id": denom.id, "name": denom.name})

    # Get current state object for display
    current_state = None
    if state_filter:
        current_state = State.objects.filter(code=state_filter).first()

    context = {
        "page_obj": page_obj,
        "denominations": denominations,
        "census_families": census_families,
        "states": states,
        "counties_by_state_json": json.dumps(counties_by_state),
        "denominations_by_family_json": json.dumps(denominations_by_family),
        "search": search,
        "denomination_filter": denomination_filter,
        "family_filter": family_filter,
        "location_filter": state_filter,
        "county_filter": county_filter,
        "current_state": current_state,
        "has_image": has_image,
        "total_records": paginator.count,
    }

    return render(request, "census/browser.html", context)


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
        family = denomination.family_census or "Other"
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

    context = {
        "states_data": states_data,
        "total_states": len(states_data),
        "total_counties": total_counties,
    }

    return render(request, "census/locations_browse.html", context)


def urban_congregations_map_view(request):
    """
    Urban American Congregations Map visualization.

    Faithful recreation of the original cities-map visualization using local Django API.
    Matches original styling, colors, layout, and functionality.
    """
    return render(request, "census/visualizations/urban_congregations_map.html")


def urban_congregations_simple_view(request):
    """
    Simplified Urban Congregations Map visualization.

    Self-contained template with inline JavaScript using local Django API.
    Much simpler to maintain than separate JS modules.
    """
    return render(request, "census/visualizations/urban_congregations_simple.html")
