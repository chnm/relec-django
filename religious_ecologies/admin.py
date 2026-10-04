import asyncio

from django.contrib import admin
from django.db.models import Count

from census.models import CensusSchedule
from census.transcription.status import with_ai_status
from census.transcription.usage import usage_report
from census.workflow import is_reviewer


def _get_dashboard_data_sync(include_ai_usage=False):
    """Get dashboard data - synchronous version for DB queries"""
    # Get transcription status counts
    status_counts = list(
        CensusSchedule.objects.values("transcription_status").annotate(
            count=Count("id")
        )
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
    approved_count = status_counts_complete["approved"]
    approval_percentage = round(
        (approved_count / total_records * 100) if total_records > 0 else 0, 1
    )
    ai_ready_review_count = (
        with_ai_status(CensusSchedule.objects.all())
        .filter(_ai_status="transcribed")
        .count()
        if include_ai_usage
        else None
    )

    # Get top transcribers
    top_transcribers = list(
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
    recent_activity = list(
        CensusSchedule.objects.select_related(
            "assigned_transcriber", "assigned_reviewer"
        ).order_by("-updated_at")[:10]
    )

    context = {
        "total_records": total_records,
        "ready_for_review_count": status_counts_complete["completed"],
        "imported_needs_review_count": status_counts_complete["needs_review"],
        "needs_review_count": (
            status_counts_complete["needs_review"] + status_counts_complete["completed"]
        ),
        "ai_ready_review_count": ai_ready_review_count,
        "approved_count": approved_count,
        "unassigned_count": status_counts_complete["unassigned"],
        "assigned_count": status_counts_complete["assigned"],
        "approval_percentage": approval_percentage,
        "status_counts": status_counts_complete,
        "top_transcribers": top_transcribers_list,
        "recent_activity": recent_activity,
    }
    if include_ai_usage:
        context["ai_usage_report"] = usage_report()
        context["show_ai_usage"] = True
    return context


def dashboard_context(request):
    """Add dashboard context to admin index - async-safe wrapper"""
    try:
        # Check if we're in an async context
        try:
            asyncio.get_running_loop()
            # We're in async context - can't call sync DB code directly
            # Return empty context for now (Unfold will handle async properly in future)
            return {}
        except RuntimeError:
            # No running loop - we're in sync context, safe to call DB
            return _get_dashboard_data_sync(include_ai_usage=is_reviewer(request.user))
    except Exception as e:
        print(f"Dashboard context error: {e}")
        return {}


# Monkey patch the admin site to add our context
original_index = admin.site.index


def custom_index(request, extra_context=None):
    extra_context = extra_context or {}
    extra_context.update(dashboard_context(request))
    return original_index(request, extra_context)


admin.site.index = custom_index
