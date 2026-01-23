import markdown
from django.views.generic import DetailView, ListView

from .models import BlogPost, Visualization


class BlogListView(ListView):
    model = BlogPost
    template_name = "pages/blog_list.html"
    context_object_name = "posts"
    paginate_by = 10

    def get_queryset(self):
        return BlogPost.objects.filter(is_draft=False).order_by("-published_date")


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


class VisualizationListView(ListView):
    model = Visualization
    template_name = "pages/visualization_list.html"
    context_object_name = "visualizations"
    paginate_by = 10

    def get_queryset(self):
        return Visualization.objects.all().order_by("-published_date")


class VisualizationDetailView(DetailView):
    model = Visualization
    template_name = "pages/visualization_detail.html"
    context_object_name = "visualization"
    slug_field = "slug"

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
        return context
