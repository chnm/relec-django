import csv

from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Count, Q, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from census.models import CensusSchedule, Denomination, ReligiousBody
from location.models import Location


def is_staff_or_reviewer(user):
    """Check if user is staff or in Reviewers group"""
    return user.is_staff or user.groups.filter(name="Reviewers").exists()


@login_required
@user_passes_test(is_staff_or_reviewer)
def analytics_home(request):
    """Main analytics dashboard"""
    context = {
        "title": "Data Analytics & Explorer",
        "total_schedules": CensusSchedule.objects.count(),
        "total_religious_bodies": ReligiousBody.objects.count(),
        "total_denominations": Denomination.objects.count(),
        "total_locations": Location.objects.count(),
    }
    return render(request, "analytics/home.html", context)


@login_required
@user_passes_test(is_staff_or_reviewer)
def query_builder(request):
    """Advanced query builder interface"""
    # Get filter options
    denominations = Denomination.objects.all().order_by("name")
    states = (
        Location.objects.values_list("state", flat=True).distinct().order_by("state")
    )

    # Get distinct denomination families
    family_census_list = (
        Denomination.objects.exclude(family_census__isnull=True)
        .exclude(family_census="")
        .values_list("family_census", flat=True)
        .distinct()
        .order_by("family_census")
    )

    family_relec_list = (
        Denomination.objects.exclude(family_relec__isnull=True)
        .exclude(family_relec="")
        .values_list("family_relec", flat=True)
        .distinct()
        .order_by("family_relec")
    )

    # Group denominations by family_relec for better organization
    denominations_by_family = {}
    for denom in denominations:
        family = denom.family_relec or "Other"
        if family not in denominations_by_family:
            denominations_by_family[family] = []
        denominations_by_family[family].append(denom)

    context = {
        "title": "Query Builder",
        "denominations": denominations,
        "denominations_by_family": dict(sorted(denominations_by_family.items())),
        "family_census_list": family_census_list,
        "family_relec_list": family_relec_list,
        "states": states,
        "transcription_statuses": CensusSchedule.TRANSCRIPTION_STATUS_CHOICES,
    }

    return render(request, "analytics/query_builder.html", context)


@login_required
@user_passes_test(is_staff_or_reviewer)
@require_http_methods(["GET", "POST"])
def run_query(request):
    """Execute advanced query and return results"""
    # Start with all religious bodies
    queryset = ReligiousBody.objects.select_related(
        "census_record", "denomination", "location"
    ).prefetch_related("membership", "census_record__clergy")

    # Apply denomination filters (support families OR individual denominations)
    family_census = request.GET.getlist("family_census")
    family_relec = request.GET.getlist("family_relec")
    denomination_ids = request.GET.getlist("denomination")

    # Build Q objects for OR logic across different denomination filter types
    denomination_filters = Q()
    if family_census:
        denomination_filters |= Q(denomination__family_census__in=family_census)
    if family_relec:
        denomination_filters |= Q(denomination__family_relec__in=family_relec)
    if denomination_ids:
        denomination_filters |= Q(denomination_id__in=denomination_ids)

    if denomination_filters:
        queryset = queryset.filter(denomination_filters)

    state = request.GET.get("state")
    if state:
        queryset = queryset.filter(location__state=state)

    county = request.GET.get("county")
    if county:
        queryset = queryset.filter(location__county__icontains=county)

    city = request.GET.get("city")
    if city:
        queryset = queryset.filter(location__city__icontains=city)

    transcription_status = request.GET.get("transcription_status")
    if transcription_status:
        queryset = queryset.filter(
            census_record__transcription_status=transcription_status
        )

    # Has membership data filter
    has_membership = request.GET.get("has_membership")
    if has_membership == "yes":
        queryset = queryset.filter(membership__isnull=False).distinct()
    elif has_membership == "no":
        queryset = queryset.filter(membership__isnull=True)

    # Has clergy data filter
    has_clergy = request.GET.get("has_clergy")
    if has_clergy == "yes":
        queryset = queryset.filter(census_record__clergy__isnull=False).distinct()
    elif has_clergy == "no":
        queryset = queryset.filter(census_record__clergy__isnull=True)

    # Property value ranges
    min_edifice_value = request.GET.get("min_edifice_value")
    if min_edifice_value:
        queryset = queryset.filter(edifice_value__gte=float(min_edifice_value))

    max_edifice_value = request.GET.get("max_edifice_value")
    if max_edifice_value:
        queryset = queryset.filter(edifice_value__lte=float(max_edifice_value))

    # Get format parameter
    export_format = request.GET.get("format", "html")

    # Limit results for HTML view
    if export_format == "html":
        total_count = queryset.count()
        queryset = queryset[:100]  # Limit to 100 for display
    else:
        total_count = queryset.count()

    if export_format == "csv":
        return export_to_csv(queryset)
    elif export_format == "json":
        return export_to_json(queryset)

    # HTML response
    context = {
        "title": "Query Results",
        "results": queryset,
        "total_count": total_count,
        "showing_count": queryset.count() if export_format == "html" else total_count,
    }

    return render(request, "analytics/query_results.html", context)


@login_required
@user_passes_test(is_staff_or_reviewer)
def denomination_analysis(request):
    """Analyze data by denomination"""
    denominations = (
        Denomination.objects.annotate(
            total_bodies=Count("religiousbody"),
            total_edifices=Sum("religiousbody__num_edifices"),
            total_edifice_value=Sum("religiousbody__edifice_value"),
        )
        .filter(total_bodies__gt=0)
        .order_by("-total_bodies")
    )

    context = {
        "title": "Denomination Analysis",
        "denominations": denominations,
    }

    return render(request, "analytics/denomination_analysis.html", context)


@login_required
@user_passes_test(is_staff_or_reviewer)
def location_analysis(request):
    """Analyze data by location (state/county)"""
    state = request.GET.get("state")

    if state:
        # County-level analysis for selected state
        counties = (
            ReligiousBody.objects.filter(location__state=state)
            .values("location__county")
            .annotate(
                total_bodies=Count("id"),
                total_denominations=Count("denomination", distinct=True),
            )
            .order_by("-total_bodies")
        )

        context = {
            "title": f"Location Analysis - {state}",
            "state": state,
            "counties": counties,
        }
        template = "analytics/county_analysis.html"
    else:
        # State-level analysis
        states = (
            ReligiousBody.objects.filter(location__isnull=False)
            .values("location__state")
            .annotate(
                total_bodies=Count("id"),
                total_denominations=Count("denomination", distinct=True),
            )
            .order_by("-total_bodies")
        )

        context = {
            "title": "Location Analysis - By State",
            "states": states,
        }
        template = "analytics/state_analysis.html"

    return render(request, template, context)


def export_to_csv(queryset):
    """Export queryset to CSV"""
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="query_results.csv"'

    writer = csv.writer(response)
    writer.writerow(
        [
            "Schedule ID",
            "Religious Body Name",
            "Denomination",
            "State",
            "County",
            "City",
            "Address",
            "Num Edifices",
            "Edifice Value",
            "Transcription Status",
            "Admin Link",
        ]
    )

    for rb in queryset:
        writer.writerow(
            [
                rb.census_record.schedule_id if rb.census_record else "",
                rb.name or "",
                rb.denomination.name if rb.denomination else "",
                rb.location.state if rb.location else "",
                rb.location.county if rb.location else "",
                rb.location.city if rb.location else "",
                rb.address or "",
                rb.num_edifices or "",
                rb.edifice_value or "",
                rb.census_record.get_transcription_status_display()
                if rb.census_record
                else "",
                f"/admin/census/censusschedule/{rb.census_record.id}/change/"
                if rb.census_record
                else "",
            ]
        )

    return response


def export_to_json(queryset):
    """Export queryset to JSON"""
    data = []

    for rb in queryset:
        data.append(
            {
                "schedule_id": rb.census_record.schedule_id
                if rb.census_record
                else None,
                "religious_body_name": rb.name,
                "denomination": rb.denomination.name if rb.denomination else None,
                "location": {
                    "state": rb.location.state if rb.location else None,
                    "county": rb.location.county if rb.location else None,
                    "city": rb.location.city if rb.location else None,
                },
                "address": rb.address,
                "num_edifices": rb.num_edifices,
                "edifice_value": float(rb.edifice_value) if rb.edifice_value else None,
                "transcription_status": rb.census_record.transcription_status
                if rb.census_record
                else None,
                "admin_url": f"/admin/census/censusschedule/{rb.census_record.id}/change/"
                if rb.census_record
                else None,
            }
        )

    return JsonResponse(
        {"results": data, "count": len(data)}, json_dumps_params={"indent": 2}
    )


@login_required
@user_passes_test(is_staff_or_reviewer)
def data_completeness(request):
    """Analyze data completeness across the dataset"""
    total_schedules = CensusSchedule.objects.count()

    # Count schedules with various types of data
    with_religious_bodies = (
        CensusSchedule.objects.filter(church_details__isnull=False).distinct().count()
    )

    with_membership = (
        CensusSchedule.objects.filter(membership_details__isnull=False)
        .distinct()
        .count()
    )

    with_clergy = CensusSchedule.objects.filter(clergy__isnull=False).distinct().count()

    with_location = ReligiousBody.objects.filter(location__isnull=False).count()
    total_religious_bodies = ReligiousBody.objects.count()

    with_county = (
        ReligiousBody.objects.filter(
            location__isnull=False, location__county__isnull=False
        )
        .exclude(location__county="")
        .count()
    )

    context = {
        "title": "Data Completeness Analysis",
        "total_schedules": total_schedules,
        "completeness": {
            "religious_bodies": {
                "count": with_religious_bodies,
                "percentage": round((with_religious_bodies / total_schedules * 100), 1)
                if total_schedules > 0
                else 0,
            },
            "membership": {
                "count": with_membership,
                "percentage": round((with_membership / total_schedules * 100), 1)
                if total_schedules > 0
                else 0,
            },
            "clergy": {
                "count": with_clergy,
                "percentage": round((with_clergy / total_schedules * 100), 1)
                if total_schedules > 0
                else 0,
            },
            "location": {
                "count": with_location,
                "percentage": round((with_location / total_religious_bodies * 100), 1)
                if total_religious_bodies > 0
                else 0,
            },
            "county": {
                "count": with_county,
                "percentage": round((with_county / total_religious_bodies * 100), 1)
                if total_religious_bodies > 0
                else 0,
            },
        },
    }

    return render(request, "analytics/data_completeness.html", context)
