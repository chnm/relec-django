import markdown
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.views.generic import DetailView, ListView

from .models import BlogPost, Page


# Static Pages
def page_detail(request, slug):
    """Display a single page by slug"""
    page = get_object_or_404(Page, slug=slug)

    # Check if page should be visible
    if not page.is_live:
        # Only show unpublished pages to staff users
        if not (request.user.is_authenticated and request.user.is_staff):
            raise Http404("Page not found")

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
@method_decorator(cache_page(60 * 15), name="dispatch")
class BlogListView(ListView):
    model = BlogPost
    template_name = "pages/blog_list.html"
    context_object_name = "posts"
    paginate_by = 10

    def get_queryset(self):
        return BlogPost.objects.filter(is_draft=False).order_by("-published_date")


@method_decorator(cache_page(60 * 15), name="dispatch")
class BlogDetailView(DetailView):
    model = BlogPost
    template_name = "pages/blog_detail.html"
    context_object_name = "post"
    slug_field = "slug"

    def get_queryset(self):
        return BlogPost.objects.filter(is_draft=False)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        md = markdown.Markdown(
            extensions=["extra", "codehilite", "toc"]
        )
        context["content_html"] = md.convert(self.object.content)
        return context
