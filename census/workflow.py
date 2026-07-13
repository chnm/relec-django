TRANSCRIBER_ACTIONS = {"mark_in_progress", "mark_completed"}
LOCKED_FOR_TRANSCRIBERS = {"needs_review", "completed", "approved"}


def is_transcriber_only(user):
    """Return whether a user has the transcriber role without a reviewer role."""
    groups = set(user.groups.values_list("name", flat=True))
    return not user.is_superuser and groups == {"Transcribers"}


def is_reviewer(user):
    """Return whether a user can perform PI/editor workflow actions."""
    return user.is_superuser or user.groups.filter(name="Reviewers").exists()


def schedules_with_religious_bodies(queryset):
    """Return schedules that contain the minimum data required for review."""
    return queryset.filter(church_details__isnull=False).distinct()
