"""
Context processors for pages app.
Makes dynamic page navigation available to all templates.
"""

from pages.models import Page


def navigation_pages(request):
    """Add pages that should show in navigation to template context"""
    nav_pages = Page.objects.filter(show_in_nav=True, is_published=True).order_by(
        "nav_order", "title"
    )

    return {
        "nav_pages": nav_pages,
    }
