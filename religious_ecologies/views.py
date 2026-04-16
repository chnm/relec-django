from django.db.models import Count
from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.cache import cache_page

from census.models import CensusSchedule, Denomination, ReligiousBody


ROBOTS_TXT = """\
User-agent: *
Allow: /

# Block AI/LLM training crawlers
User-agent: GPTBot
Disallow: /

User-agent: ChatGPT-User
Disallow: /

User-agent: Google-Extended
Disallow: /

User-agent: CCBot
Disallow: /

User-agent: anthropic-ai
Disallow: /

User-agent: ClaudeBot
Disallow: /

User-agent: Bytespider
Disallow: /

User-agent: Meta-ExternalAgent
Disallow: /

User-agent: PerplexityBot
Disallow: /

User-agent: Applebot-Extended
Disallow: /

User-agent: cohere-ai
Disallow: /

User-agent: Diffbot
Disallow: /

User-agent: FacebookBot
Disallow: /

User-agent: Omgilibot
Disallow: /

User-agent: Amazonbot
Disallow: /

# Rate-limit aggressive crawlers on detail pages
User-agent: *
Crawl-delay: 2

Sitemap: https://religiousecologies.org/sitemap.xml
"""


@cache_page(60 * 60 * 24)  # Cache for 24 hours
def robots_txt(request):
    return HttpResponse(ROBOTS_TXT, content_type="text/plain")


@cache_page(60 * 15)  # 15 minutes
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

    # Get top 25 counties by schedule count
    top_counties = (
        CensusSchedule.objects.filter(county__isnull=False)
        .values("county__name", "county__state__code")
        .annotate(schedule_count=Count("id"))
        .filter(schedule_count__gt=0)
        .order_by("-schedule_count")[:25]
    )

    # Get total unique counties
    total_counties = (
        CensusSchedule.objects.filter(county__isnull=False)
        .values("county", "county__state")
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
