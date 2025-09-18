from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, render

from .models import CensusSchedule, Denomination, ReligiousBody


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


def census_browser_view(request):
    """Render the census records browser with filtering and pagination"""

    # Get filter parameters
    search = request.GET.get("search", "")
    denomination_filter = request.GET.get("denomination", "")
    family_filter = request.GET.get("family", "")
    location_filter = request.GET.get("location", "")
    has_image = request.GET.get("has_image", "")

    # Base queryset with related data
    queryset = (
        CensusSchedule.objects.select_related()
        .prefetch_related(
            "church_details__denomination",
            "church_details__location",
            "membership_details",
            "clergy",
        )
        .order_by("-created_at")
    )

    # Apply filters
    if search:
        queryset = queryset.filter(
            Q(schedule_title__icontains=search)
            | Q(church_details__name__icontains=search)
            | Q(church_details__denomination__name__icontains=search)
            | Q(notes__icontains=search)
        )

    if denomination_filter:
        queryset = queryset.filter(church_details__denomination_id=denomination_filter)

    if family_filter:
        queryset = queryset.filter(
            church_details__denomination__family_census=family_filter
        )

    if location_filter:
        queryset = queryset.filter(
            church_details__location__state__icontains=location_filter
        )

    if has_image == "yes":
        queryset = queryset.exclude(original_image__isnull=True).exclude(
            original_image=""
        )
    elif has_image == "no":
        queryset = queryset.filter(
            Q(original_image__isnull=True) | Q(original_image="")
        )

    # Pagination
    paginator = Paginator(queryset, 20)  # Show 20 records per page
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    # Get filter options
    denominations = Denomination.objects.all().order_by("name")
    census_families = (
        Denomination.objects.values_list("family_census", flat=True)
        .distinct()
        .order_by("family_census")
    )

    context = {
        "page_obj": page_obj,
        "denominations": denominations,
        "census_families": census_families,
        "search": search,
        "denomination_filter": denomination_filter,
        "family_filter": family_filter,
        "location_filter": location_filter,
        "has_image": has_image,
        "total_records": paginator.count,
    }

    return render(request, "census/browser.html", context)


def census_detail_view(request, resource_id):
    """Render detailed view of a single census record"""

    census_record = get_object_or_404(
        CensusSchedule.objects.select_related().prefetch_related(
            "church_details__denomination",
            "church_details__location",
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

    # Get state-level counts
    states_with_counts = (
        ReligiousBody.objects.filter(location__isnull=False)
        .values("location__state")
        .annotate(schedule_count=Count("census_record"))
        .filter(schedule_count__gt=0)
        .order_by("location__state")
    )

    # Get county-level counts for each state
    counties_with_counts = (
        ReligiousBody.objects.filter(location__isnull=False)
        .values("location__state", "location__county")
        .annotate(schedule_count=Count("census_record"))
        .filter(schedule_count__gt=0)
        .order_by("location__state", "location__county")
    )

    # Group counties by state
    states_data = {}
    for state in states_with_counts:
        state_name = state["location__state"]
        states_data[state_name] = {
            "total_count": state["schedule_count"],
            "counties": [],
        }

    for county in counties_with_counts:
        state_name = county["location__state"]
        if state_name in states_data:
            states_data[state_name]["counties"].append(
                {"name": county["location__county"], "count": county["schedule_count"]}
            )

    context = {
        "states_data": states_data,
        "total_states": len(states_data),
    }

    return render(request, "census/locations_browse.html", context)
