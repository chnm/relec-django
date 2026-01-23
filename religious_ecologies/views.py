from django.db.models import Count
from django.shortcuts import render

from census.models import CensusSchedule, Denomination, ReligiousBody


def index(request):
    # Get summary statistics
    total_schedules = CensusSchedule.objects.count()
    total_denominations = Denomination.objects.count()
    schedules_with_images = (
        CensusSchedule.objects.exclude(original_image__isnull=True)
        .exclude(original_image="")
        .count()
    )

    # Calculate completion percentage
    completion_percentage = (
        (schedules_with_images / total_schedules * 100) if total_schedules > 0 else 0
    )

    # Get top 25 denominations by schedule count
    top_denominations = (
        Denomination.objects.annotate(
            schedule_count=Count("religiousbody__census_record")
        )
        .filter(schedule_count__gt=0)
        .order_by("-schedule_count")[:25]
    )

    # Get top 25 counties by schedule count (using location data)
    top_counties = (
        ReligiousBody.objects.filter(location__isnull=False)
        .values("location__county", "location__state")
        .annotate(schedule_count=Count("census_record"))
        .filter(schedule_count__gt=0)
        .order_by("-schedule_count")[:25]
    )

    # Get total unique counties
    total_counties = (
        ReligiousBody.objects.filter(location__isnull=False)
        .values("location__county", "location__state")
        .distinct()
        .count()
    )

    context = {
        "total_schedules": total_schedules,
        "total_denominations": total_denominations,
        "total_counties": total_counties,
        "schedules_with_images": schedules_with_images,
        "completion_percentage": round(completion_percentage, 1),
        "top_denominations": top_denominations,
        "top_counties": top_counties,
    }

    return render(request, "index.html", context)
