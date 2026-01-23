from django.contrib import admin
from django.db.models import Count

from census.models import CensusSchedule


def dashboard_context(request):
    """Add dashboard context to admin index"""

    # Get transcription status counts
    status_counts = CensusSchedule.objects.values("transcription_status").annotate(
        count=Count("id")
    )
    status_dict = {
        item["transcription_status"]: item["count"] for item in status_counts
    }

    # Ensure all statuses are represented
    all_statuses = [
        "unassigned",
        "assigned",
        "in_progress",
        "needs_review",
        "completed",
        "approved",
    ]
    status_counts_complete = {
        status: status_dict.get(status, 0) for status in all_statuses
    }

    # Calculate totals
    total_records = CensusSchedule.objects.count()
    transcribed_count = (
        status_counts_complete["completed"] + status_counts_complete["approved"]
    )
    completion_percentage = round(
        (transcribed_count / total_records * 100) if total_records > 0 else 0, 1
    )

    # Get top transcribers
    top_transcribers = (
        CensusSchedule.objects.filter(assigned_transcriber__isnull=False)
        .values("assigned_transcriber__username")
        .annotate(count=Count("id"))
        .order_by("-count")[:5]
    )

    # Fix the query structure for template usage
    top_transcribers_list = []
    for item in top_transcribers:
        top_transcribers_list.append(
            {
                "user__username": item["assigned_transcriber__username"],
                "count": item["count"],
            }
        )

    # Recent activity (last 10 updated records)
    recent_activity = CensusSchedule.objects.select_related(
        "assigned_transcriber", "assigned_reviewer"
    ).order_by("-updated_at")[:10]

    return {
        "total_records": total_records,
        "transcribed_count": transcribed_count,
        "needs_review_count": status_counts_complete["needs_review"],
        "unassigned_count": status_counts_complete["unassigned"],
        "assigned_count": status_counts_complete["assigned"],
        "completion_percentage": completion_percentage,
        "status_counts": status_counts_complete,
        "top_transcribers": top_transcribers_list,
        "recent_activity": recent_activity,
    }


# Monkey patch the admin site to add our context
original_index = admin.site.index


def custom_index(request, extra_context=None):
    extra_context = extra_context or {}
    extra_context.update(dashboard_context(request))
    return original_index(request, extra_context)


admin.site.index = custom_index
