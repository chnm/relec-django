from django.http import Http404
from django.shortcuts import get_object_or_404, render

from .models import Page


def page_detail(request, slug):
    """Display a single page by slug"""
    page = get_object_or_404(Page, slug=slug)

    # Check if page should be visible
    if not page.is_live:
        # Only show unpublished pages to staff users
        if not (request.user.is_authenticated and request.user.is_staff):
            raise Http404("Page not found")

    # Set page title for template
    context = {
        "page": page,
        "page_title": page.title,
        "meta_description": page.meta_description,
    }

    return render(request, "pages/detail.html", context)


def get_nav_pages():
    """Helper function to get pages that should show in navigation"""
    return Page.objects.filter(show_in_nav=True, is_published=True).order_by(
        "nav_order", "title"
    )


# Context processor to make nav pages available in all templates
def nav_pages_context(request):
    """Context processor to add navigation pages to all templates"""
    return {"nav_pages": get_nav_pages()}
