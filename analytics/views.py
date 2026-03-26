import csv

from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Count, Q, Subquery, Sum
from django.db.models.functions import Coalesce
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods
from django_tables2 import RequestConfig

from analytics.tables import ReligiousBodyTable
from census.models import CensusSchedule, Denomination, ReligiousBody
from location.models import County, PopulatedPlace, State


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
        "total_states": State.objects.count(),
        "total_counties": County.objects.count(),
        "total_places": PopulatedPlace.objects.count(),
    }
    return render(request, "analytics/home.html", context)


@login_required
@user_passes_test(is_staff_or_reviewer)
def query_builder(request):
    """Advanced query builder interface"""
    # Get filter options
    denominations = Denomination.objects.all().order_by("name")
    states = State.objects.all().order_by("name")

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
        "census_record",
        "census_record__county",
        "census_record__county__state",
        "census_record__populated_place",
        "denomination",
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
        queryset = queryset.filter(census_record__county__state__code=state)

    county = request.GET.get("county")
    if county:
        queryset = queryset.filter(census_record__county__name__icontains=county)

    city = request.GET.get("city")
    if city:
        queryset = queryset.filter(census_record__populated_place__name__icontains=city)

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

    # Has location data filter (location is now on census_record)
    has_location = request.GET.get("has_location")
    if has_location == "yes":
        queryset = queryset.filter(census_record__county__isnull=False)
    elif has_location == "no":
        queryset = queryset.filter(census_record__county__isnull=True)

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
def transcription_progress(request):
    """Breakdown of transcription progress by denomination."""
    from django.db.models import IntegerField, OuterRef

    # Use subqueries to avoid cross-join explosion from multiple annotations
    census_count = (
        CensusSchedule.objects.filter(schedule_denomination=OuterRef("pk"))
        .order_by()
        .values("schedule_denomination")
        .annotate(c=Count("*"))
        .values("c")
    )
    body_count = (
        ReligiousBody.objects.filter(denomination=OuterRef("pk"))
        .order_by()
        .values("denomination")
        .annotate(c=Count("*"))
        .values("c")
    )
    in_progress_count = (
        CensusSchedule.objects.filter(
            schedule_denomination=OuterRef("pk"),
            transcription_status="in_progress",
        )
        .order_by()
        .values("schedule_denomination")
        .annotate(c=Count("*"))
        .values("c")
    )
    approved_count = (
        CensusSchedule.objects.filter(
            schedule_denomination=OuterRef("pk"),
            transcription_status="approved",
        )
        .order_by()
        .values("schedule_denomination")
        .annotate(c=Count("*"))
        .values("c")
    )

    denominations = (
        Denomination.objects.annotate(
            total_census=Coalesce(
                Subquery(census_count, output_field=IntegerField()), 0
            ),
            total_in_database=Coalesce(
                Subquery(body_count, output_field=IntegerField()), 0
            ),
            total_in_progress=Coalesce(
                Subquery(in_progress_count, output_field=IntegerField()), 0
            ),
            total_transcribed=Coalesce(
                Subquery(approved_count, output_field=IntegerField()), 0
            ),
        )
        .filter(total_census__gt=0)
        .order_by("family_relec", "name")
    )

    # Compute totals for the summary row
    totals = denominations.aggregate(
        grand_census=Sum("total_census"),
        grand_database=Sum("total_in_database"),
        grand_in_progress=Sum("total_in_progress"),
        grand_transcribed=Sum("total_transcribed"),
    )

    # Group denominations by family_relec for the template
    from collections import OrderedDict

    families = OrderedDict()
    for denom in denominations:
        family = denom.family_relec or "Uncategorized"
        if family not in families:
            families[family] = {
                "denominations": [],
                "total_census": 0,
                "total_in_database": 0,
                "total_in_progress": 0,
                "total_transcribed": 0,
            }
        families[family]["denominations"].append(denom)
        families[family]["total_census"] += denom.total_census
        families[family]["total_in_database"] += denom.total_in_database
        families[family]["total_in_progress"] += denom.total_in_progress
        families[family]["total_transcribed"] += denom.total_transcribed

    context = {
        "title": "Transcription Progress by Denomination",
        "families": families,
        "totals": totals,
    }

    return render(request, "analytics/transcription_progress.html", context)


@login_required
@user_passes_test(is_staff_or_reviewer)
def location_analysis(request):
    """Analyze data by location (state/county)"""
    state = request.GET.get("state")

    if state:
        # County-level analysis for selected state
        counties = (
            ReligiousBody.objects.filter(census_record__county__state__code=state)
            .values("census_record__county__name")
            .annotate(
                total_bodies=Count("id"),
                total_denominations=Count("denomination", distinct=True),
            )
            .order_by("-total_bodies")
        )

        # Get state name for display
        state_obj = State.objects.filter(code=state).first()
        state_name = state_obj.name if state_obj else state

        context = {
            "title": f"Location Analysis - {state_name}",
            "state": state,
            "state_name": state_name,
            "counties": counties,
        }
        template = "analytics/county_analysis.html"
    else:
        # State-level analysis
        states = (
            ReligiousBody.objects.filter(census_record__county__isnull=False)
            .values(
                "census_record__county__state__code",
                "census_record__county__state__name",
            )
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
            "Place",
            "Address",
            "Num Edifices",
            "Edifice Value",
            "Transcription Status",
            "Admin Link",
        ]
    )

    for rb in queryset:
        # Get location from census_record
        state = ""
        county = ""
        place = ""
        if rb.census_record:
            if rb.census_record.county:
                county = rb.census_record.county.name
                if rb.census_record.county.state:
                    state = rb.census_record.county.state.code
            if rb.census_record.populated_place:
                place = rb.census_record.populated_place.name

        writer.writerow(
            [
                rb.census_record.schedule_id if rb.census_record else "",
                rb.name or "",
                rb.denomination.name if rb.denomination else "",
                state,
                county,
                place,
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
        # Get location from census_record
        location_data = {"state": None, "county": None, "place": None}
        if rb.census_record:
            if rb.census_record.county:
                location_data["county"] = rb.census_record.county.name
                if rb.census_record.county.state:
                    location_data["state"] = rb.census_record.county.state.code
            if rb.census_record.populated_place:
                location_data["place"] = rb.census_record.populated_place.name

        data.append(
            {
                "schedule_id": rb.census_record.schedule_id
                if rb.census_record
                else None,
                "religious_body_name": rb.name,
                "denomination": rb.denomination.name if rb.denomination else None,
                "location": location_data,
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
    total_places = PopulatedPlace.objects.count()

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

    # Core Data metrics - location now on CensusSchedule
    with_county = CensusSchedule.objects.filter(county__isnull=False).count()
    with_place = CensusSchedule.objects.filter(populated_place__isnull=False).count()
    with_denomination = ReligiousBody.objects.filter(denomination__isnull=False).count()
    with_name = ReligiousBody.objects.exclude(Q(name__isnull=True) | Q(name="")).count()
    with_address = ReligiousBody.objects.exclude(
        Q(address__isnull=True) | Q(address="")
    ).count()

    # Assets metrics
    with_images = CensusSchedule.objects.exclude(
        Q(original_image__isnull=True) | Q(original_image="")
    ).count()

    places_with_place_id = PopulatedPlace.objects.filter(place_id__isnull=False).count()

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
        "total_places": total_places,
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
            # Core Data - location now on schedules
            "county": {
                "count": with_county,
                "percentage": round((with_county / total_schedules * 100), 1)
                if total_schedules > 0
                else 0,
            },
            "place": {
                "count": with_place,
                "percentage": round((with_place / total_schedules * 100), 1)
                if total_schedules > 0
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
                "count": places_with_place_id,
                "percentage": round((places_with_place_id / total_places * 100), 1)
                if total_places > 0
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
    """Show populated places that don't have place_id attached"""
    # Get places without place_id
    places_without_place_id = (
        PopulatedPlace.objects.filter(Q(place_id__isnull=True))
        .select_related("county", "county__state")
        .annotate(usage_count=Count("census_schedules"))
        .order_by("-usage_count", "county__state__code", "county__name", "name")
    )

    # Get statistics
    total_places = PopulatedPlace.objects.count()
    missing_count = places_without_place_id.count()

    # Count how many schedules are affected
    affected_schedules = CensusSchedule.objects.filter(
        populated_place__place_id__isnull=True
    ).count()

    missing_percentage = (
        round((missing_count / total_places * 100), 1) if total_places > 0 else 0
    )
    completeness_percentage = (
        round(100 - missing_percentage, 1) if total_places > 0 else 100
    )

    context = {
        "title": "Places Missing Place IDs",
        "places": places_without_place_id,
        "total_places": total_places,
        "missing_count": missing_count,
        "missing_percentage": missing_percentage,
        "completeness_percentage": completeness_percentage,
        "affected_schedules": affected_schedules,
    }

    return render(request, "analytics/missing_place_ids.html", context)
