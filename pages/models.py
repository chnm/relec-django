from django.db import models
from django.urls import reverse
from django.utils.text import slugify
from simple_history.models import HistoricalRecords


class Page(models.Model):
    """
    Static CMS pages (e.g., About, Datasets).
    Content stored as HTML.
    """

    title = models.CharField(
        max_length=200, help_text="Page title (shown in browser tab and as heading)"
    )
    slug = models.SlugField(
        unique=True,
        max_length=200,
        help_text="URL path (e.g., 'datasets' for /datasets/). Leave blank to auto-generate from title.",
    )
    content = models.TextField(
        help_text="Page content as Markdown. HTML is allowed for formatting."
    )
    meta_description = models.CharField(
        max_length=160,
        blank=True,
        help_text="Brief description for search engines (160 characters max)",
    )

    # Publishing controls
    is_published = models.BooleanField(
        default=True, help_text="Uncheck to hide this page from public view"
    )
    publish_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Optional: Schedule when this page should go live",
    )

    # Navigation controls
    show_in_nav = models.BooleanField(
        default=False, help_text="Check to show this page in the main navigation menu"
    )
    nav_title = models.CharField(
        max_length=50,
        blank=True,
        help_text="Short title for navigation (leave blank to use main title)",
    )
    nav_order = models.IntegerField(
        default=0, help_text="Order in navigation menu (lower numbers appear first)"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Track changes with simple_history (who changed what when)
    history = HistoricalRecords()

    class Meta:
        ordering = ["nav_order", "title"]
        verbose_name = "Page"
        verbose_name_plural = "Pages"

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        # Auto-generate slug from title if not provided
        if not self.slug:
            base_slug = slugify(self.title)
            slug = base_slug
            counter = 1

            # Make sure slug is unique
            while Page.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1

            self.slug = slug

        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("page_detail", kwargs={"slug": self.slug})

    def get_nav_title(self):
        """Return the navigation title or fall back to main title"""
        return self.nav_title if self.nav_title else self.title

    @property
    def is_live(self):
        """Check if page should be visible to public"""
        if not self.is_published:
            return False

        if self.publish_date:
            from django.utils import timezone

            return self.publish_date <= timezone.now()

        return True


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
        max_length=500,
        blank=True,
        help_text="DEPRECATED: Path to featured image (use thumbnail_image instead)",
    )
    thumbnail_image = models.ImageField(
        upload_to="blog/thumbnails/",
        blank=True,
        null=True,
        help_text="Thumbnail image for blog post listings",
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
        return reverse("blog-detail", kwargs={"slug": self.slug})

    def get_thumbnail_url(self):
        """Return thumbnail URL, preferring uploaded image over static path"""
        if self.thumbnail_image:
            return self.thumbnail_image.url
        return self.featured_image if self.featured_image else None


class Visualization(models.Model):
    """
    Interactive visualizations with D3.js and associated assets.
    Content stored as Markdown.
    """

    title = models.CharField(max_length=500)
    slug = models.SlugField(max_length=200, unique=True)
    author = models.CharField(
        max_length=200, blank=True, help_text="Author(s) of the visualization"
    )
    published_date = models.DateTimeField()
    updated_date = models.DateTimeField(blank=True, null=True)
    content = models.TextField(help_text="Markdown content")
    abstract = models.TextField()
    # thumbnail = models.CharField(
    #    max_length=500,
    #    help_text="DEPRECATED: Path to thumbnail image (use thumbnail_image instead)",
    # )
    thumbnail_image = models.ImageField(
        upload_to="visualizations/thumbnails/",
        blank=True,
        null=True,
        help_text="Thumbnail image for visualization listings",
    )
    thumbnail_description = models.CharField(max_length=500, blank=True)
    doi = models.URLField(blank=True, help_text="Digital Object Identifier")
    script_file = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        help_text="Path to JavaScript file (e.g., viz/cities-map/main.js)",
    )
    style_file = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        help_text="Path to CSS file (e.g., viz/cities-map/style.css)",
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
        return reverse("visualization-detail", kwargs={"slug": self.slug})

    def get_thumbnail_url(self):
        """Return thumbnail URL from uploaded image"""
        if self.thumbnail_image:
            return self.thumbnail_image.url
        return None
