import json

import markdown
from django.conf import settings
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.views.generic import DetailView, ListView

from .models import BlogPost, Page, Visualization


# Static Pages
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

    # Use a lazy object that only queries when accessed in templates
    # This prevents the async/sync issue with ASGI
    class LazyNavPages:
        def __iter__(self):
            return iter(get_nav_pages())

        def __len__(self):
            return get_nav_pages().count()

        def __bool__(self):
            return get_nav_pages().exists()

    return {"nav_pages": LazyNavPages()}


# Blog Posts
@method_decorator(cache_page(60 * 15), name="dispatch")  # 15 minutes
class BlogListView(ListView):
    model = BlogPost
    template_name = "pages/blog_list.html"
    context_object_name = "posts"
    paginate_by = 10

    def get_queryset(self):
        return BlogPost.objects.filter(is_draft=False).order_by("-published_date")


@method_decorator(cache_page(60 * 15), name="dispatch")  # 15 minutes
class BlogDetailView(DetailView):
    model = BlogPost
    template_name = "pages/blog_detail.html"
    context_object_name = "post"
    slug_field = "slug"

    def get_queryset(self):
        return BlogPost.objects.filter(is_draft=False)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Render markdown to HTML
        md = markdown.Markdown(
            extensions=[
                "extra",  # Tables, footnotes, etc.
                "codehilite",  # Code highlighting
                "toc",  # Table of contents
            ]
        )
        context["content_html"] = md.convert(self.object.content)
        return context


# Visualizations
@method_decorator(cache_page(60 * 15), name="dispatch")  # 15 minutes
class VisualizationListView(ListView):
    model = Visualization
    template_name = "pages/visualization_list.html"
    context_object_name = "visualizations"
    paginate_by = 10

    def get_queryset(self):
        return Visualization.objects.all().order_by("-published_date")


@method_decorator(cache_page(60 * 15), name="dispatch")  # 15 minutes
class VisualizationDetailView(DetailView):
    model = Visualization
    template_name = "pages/visualization_detail.html"
    context_object_name = "visualization"
    slug_field = "slug"

    def get_template_names(self):
        """Check for custom template based on slug, fall back to default"""
        custom_template = f"pages/visualizations/{self.object.slug}.html"
        # Try custom template first, then fall back to default
        return [custom_template, self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Render markdown to HTML
        md = markdown.Markdown(
            extensions=[
                "extra",
                "codehilite",
                "toc",
            ]
        )
        context["content_html"] = md.convert(self.object.content)

        # Load JSON data for specific visualizations
        if self.object.slug == "catholic-dioceses":
            # Try STATICFILES_DIRS first (development), then STATIC_ROOT (production)
            if hasattr(settings, "STATICFILES_DIRS") and settings.STATICFILES_DIRS:
                base_path = settings.STATICFILES_DIRS[0]
            else:
                base_path = settings.STATIC_ROOT

            dioceses_path = base_path / "data" / "catholic_dioceses.json"

            try:
                with open(dioceses_path, "r", encoding="utf-8") as f:
                    # Load and re-serialize to JSON string for template
                    context["dioceses_data"] = json.dumps(json.load(f))

                # Use CHNM API for historical state boundaries instead of embedding large GeoJSON
                # The template will fetch from: http://data.chnm.org/ahcb/states/[date]/
                context["use_chnm_api_for_map"] = True
            except (FileNotFoundError, json.JSONDecodeError) as e:
                # Gracefully handle missing or invalid data files
                context["dioceses_data"] = "[]"
                context["use_chnm_api_for_map"] = False
                # Log the error in development
                import logging

                logging.warning(f"Error loading Catholic dioceses data: {e}")

        return context
