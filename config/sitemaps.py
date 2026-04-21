from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from census.models import CensusSchedule
from location.models import State
from pages.models import BlogPost, Page
from visualizations.models import Visualization


class StaticViewSitemap(Sitemap):
    """Static pages: home, census browser, maps, browse indexes."""

    changefreq = "weekly"
    priority = 0.8

    def items(self):
        return [
            "index",
            "census_browser",
            "denomination_map",
            "demographics_map",
            "denominations_browse",
            "locations_browse",
            "urban_congregations_map",
            "api_documentation",
            "blog-list",
            "visualization-list",
        ]

    def location(self, item):
        return reverse(item)


class PageSitemap(Sitemap):
    """Published CMS pages."""

    changefreq = "monthly"
    priority = 0.6

    def items(self):
        return Page.objects.filter(is_published=True)

    def location(self, obj):
        return reverse("page_detail", kwargs={"slug": obj.slug})

    def lastmod(self, obj):
        return obj.updated_at


class BlogPostSitemap(Sitemap):
    """Published blog posts."""

    changefreq = "monthly"
    priority = 0.7

    def items(self):
        return BlogPost.objects.filter(is_draft=False)

    def location(self, obj):
        return reverse("blog-detail", kwargs={"slug": obj.slug})

    def lastmod(self, obj):
        return obj.updated_at


class VisualizationSitemap(Sitemap):
    """Published visualizations."""

    changefreq = "monthly"
    priority = 0.7

    def items(self):
        return Visualization.objects.all()

    def location(self, obj):
        return reverse("visualization-detail", kwargs={"slug": obj.slug})

    def lastmod(self, obj):
        return obj.updated_at


class CensusBrowserStateSitemap(Sitemap):
    """Census browser state-level pages."""

    changefreq = "weekly"
    priority = 0.5

    def items(self):
        return State.objects.all()

    def location(self, obj):
        return reverse("census_browser_state", kwargs={"state_code": obj.code})


class CensusDetailSitemap(Sitemap):
    """Individual census record detail pages (approved only)."""

    changefreq = "monthly"
    priority = 0.4
    limit = 1000

    def items(self):
        return CensusSchedule.objects.filter(
            transcription_status="approved"
        ).order_by("-updated_at")

    def location(self, obj):
        return reverse("census_detail", kwargs={"resource_id": obj.resource_id})

    def lastmod(self, obj):
        return obj.updated_at
