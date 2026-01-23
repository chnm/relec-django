from django.db import models
from simple_history.models import HistoricalRecords


class BlogPost(models.Model):
    """
    Blog posts migrated from Hugo site.
    Content stored as Markdown.
    """

    title = models.CharField(max_length=500)
    slug = models.SlugField(max_length=200, unique=True)
    author = models.CharField(max_length=200)
    published_date = models.DateTimeField()
    content = models.TextField(help_text="Markdown content")
    abstract = models.TextField(blank=True)
    featured_image = models.CharField(
        max_length=500, blank=True, help_text="Path to featured image"
    )
    image_alt_text = models.CharField(max_length=500, blank=True)
    is_draft = models.BooleanField(default=False)

    # Record keeping
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ["-published_date"]
        verbose_name = "Blog Post"
        verbose_name_plural = "Blog Posts"

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        from django.urls import reverse

        return reverse("blog-detail", kwargs={"slug": self.slug})


class Visualization(models.Model):
    """
    Interactive visualizations with D3.js and associated assets.
    Content stored as Markdown.
    """

    title = models.CharField(max_length=500)
    slug = models.SlugField(max_length=200, unique=True)
    published_date = models.DateTimeField()
    updated_date = models.DateTimeField(blank=True, null=True)
    content = models.TextField(help_text="Markdown content")
    abstract = models.TextField()
    thumbnail = models.CharField(max_length=500, help_text="Path to thumbnail image")
    thumbnail_description = models.CharField(max_length=500, blank=True)
    doi = models.URLField(blank=True, help_text="Digital Object Identifier")
    script_file = models.CharField(
        max_length=200,
        help_text="Path to JavaScript file (e.g., viz/cities-map/main.js)",
    )
    style_file = models.CharField(
        max_length=200, help_text="Path to CSS file (e.g., viz/cities-map/style.css)"
    )

    # Record keeping
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ["-published_date"]
        verbose_name = "Visualization"
        verbose_name_plural = "Visualizations"

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        from django.urls import reverse

        return reverse("visualization-detail", kwargs={"slug": self.slug})
