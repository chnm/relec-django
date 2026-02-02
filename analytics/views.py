import csv

from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Count, Q, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods
from django_tables2 import RequestConfig

from analytics.tables import ReligiousBodyTable
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

    # Has location data filter
    has_location = request.GET.get("has_location")
    if has_location == "yes":
        queryset = queryset.filter(location__isnull=False)
    elif has_location == "no":
        queryset = queryset.filter(location__isnull=True)

    # Property value ranges
    min_edifice_value = request.GET.get("min_edifice_value")
    if min_edifice_value:
        queryset = queryset.filter(edifice_value__gte=float(min_edifice_value))

    max_edifice_value = request.GET.get("max_edifice_value")
    if max_edifice_value:
        queryset = queryset.filter(edifice_value__lte=float(max_edifice_value))

    # Get format parameter
    export_format = request.GET.get("format", "html")

    # Handle export formats (use full queryset)
    if export_format == "csv":
        return export_to_csv(queryset)
    elif export_format == "json":
        return export_to_json(queryset)

    # Build applied filters summary for display
    applied_filters = []

    if family_census:
        applied_filters.append(
            {"label": "Census Family", "value": ", ".join(family_census)}
        )
    if family_relec:
        applied_filters.append(
            {"label": "RelEc Family", "value": ", ".join(family_relec)}
        )
    if denomination_ids:
        denoms = Denomination.objects.filter(id__in=denomination_ids).values_list(
            "name", flat=True
        )
        applied_filters.append({"label": "Denomination", "value": ", ".join(denoms)})
    if state:
        applied_filters.append({"label": "State", "value": state})
    if county:
        applied_filters.append({"label": "County", "value": county})
    if city:
        applied_filters.append({"label": "City", "value": city})
    if transcription_status:
        status_display = dict(CensusSchedule.TRANSCRIPTION_STATUS_CHOICES).get(
            transcription_status, transcription_status
        )
        applied_filters.append({"label": "Status", "value": status_display})
    if has_membership:
        applied_filters.append(
            {
                "label": "Has Membership",
                "value": "Yes" if has_membership == "yes" else "No",
            }
        )
    if has_clergy:
        applied_filters.append(
            {"label": "Has Clergy", "value": "Yes" if has_clergy == "yes" else "No"}
        )
    if has_location:
        applied_filters.append(
            {"label": "Has Location", "value": "Yes" if has_location == "yes" else "No"}
        )
    if min_edifice_value:
        applied_filters.append(
            {"label": "Min Edifice Value", "value": f"${float(min_edifice_value):,.2f}"}
        )
    if max_edifice_value:
        applied_filters.append(
            {"label": "Max Edifice Value", "value": f"${float(max_edifice_value):,.2f}"}
        )

    # HTML response with django-tables2
    total_count = queryset.count()
    table = ReligiousBodyTable(queryset)

    # Configure pagination (25 per page)
    RequestConfig(request, paginate={"per_page": 25}).configure(table)

    context = {
        "title": "Query Results",
        "table": table,
        "total_count": total_count,
        "applied_filters": applied_filters,
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
    total_religious_bodies = ReligiousBody.objects.count()
    total_locations = Location.objects.count()

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

    # Core Data metrics
    with_location = ReligiousBody.objects.filter(location__isnull=False).count()
    with_denomination = ReligiousBody.objects.filter(denomination__isnull=False).count()
    with_name = ReligiousBody.objects.exclude(Q(name__isnull=True) | Q(name="")).count()
    with_address = ReligiousBody.objects.exclude(
        Q(address__isnull=True) | Q(address="")
    ).count()

    with_county = (
        ReligiousBody.objects.filter(
            location__isnull=False, location__county__isnull=False
        )
        .exclude(location__county="")
        .count()
    )

    # Assets metrics
    with_images = CensusSchedule.objects.exclude(
        Q(original_image__isnull=True) | Q(original_image="")
    ).count()

    locations_with_place_id = Location.objects.filter(place_id__isnull=False).count()

    # Supplementary Data metrics
    with_edifice_value = ReligiousBody.objects.filter(
        edifice_value__isnull=False
    ).count()
    with_expenses = ReligiousBody.objects.filter(expenses__isnull=False).count()
    with_benevolences = ReligiousBody.objects.filter(benevolences__isnull=False).count()

    context = {
        "title": "Data Completeness Analysis",
        "total_schedules": total_schedules,
        "total_religious_bodies": total_religious_bodies,
        "total_locations": total_locations,
        "completeness": {
            # Original metrics
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
            # Core Data
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
            "denomination": {
                "count": with_denomination,
                "percentage": round(
                    (with_denomination / total_religious_bodies * 100), 1
                )
                if total_religious_bodies > 0
                else 0,
            },
            "name": {
                "count": with_name,
                "percentage": round((with_name / total_religious_bodies * 100), 1)
                if total_religious_bodies > 0
                else 0,
            },
            "address": {
                "count": with_address,
                "percentage": round((with_address / total_religious_bodies * 100), 1)
                if total_religious_bodies > 0
                else 0,
            },
            # Assets
            "images": {
                "count": with_images,
                "percentage": round((with_images / total_schedules * 100), 1)
                if total_schedules > 0
                else 0,
            },
            "place_ids": {
                "count": locations_with_place_id,
                "percentage": round(
                    (locations_with_place_id / total_locations * 100), 1
                )
                if total_locations > 0
                else 0,
            },
            # Supplementary Data
            "edifice_value": {
                "count": with_edifice_value,
                "percentage": round(
                    (with_edifice_value / total_religious_bodies * 100), 1
                )
                if total_religious_bodies > 0
                else 0,
            },
            "expenses": {
                "count": with_expenses,
                "percentage": round((with_expenses / total_religious_bodies * 100), 1)
                if total_religious_bodies > 0
                else 0,
            },
            "benevolences": {
                "count": with_benevolences,
                "percentage": round(
                    (with_benevolences / total_religious_bodies * 100), 1
                )
                if total_religious_bodies > 0
                else 0,
            },
        },
    }

    return render(request, "analytics/data_completeness.html", context)


@login_required
@user_passes_test(is_staff_or_reviewer)
def missing_place_ids(request):
    """Show locations that don't have place_id attached"""
    # Get locations without place_id
    locations_without_place_id = (
        Location.objects.filter(Q(place_id__isnull=True))
        .annotate(usage_count=Count("religiousbody"))
        .order_by("-usage_count", "state", "county", "map_name")
    )

    # Get statistics
    total_locations = Location.objects.count()
    missing_count = locations_without_place_id.count()

    # Count how many religious bodies are affected
    affected_bodies = ReligiousBody.objects.filter(
        location__place_id__isnull=True
    ).count()

    missing_percentage = (
        round((missing_count / total_locations * 100), 1) if total_locations > 0 else 0
    )
    completeness_percentage = (
        round(100 - missing_percentage, 1) if total_locations > 0 else 100
    )

    context = {
        "title": "Locations Missing Place IDs",
        "locations": locations_without_place_id,
        "total_locations": total_locations,
        "missing_count": missing_count,
        "missing_percentage": missing_percentage,
        "completeness_percentage": completeness_percentage,
        "affected_bodies": affected_bodies,
    }

    return render(request, "analytics/missing_place_ids.html", context)
