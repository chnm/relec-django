from django.db import models
from django.urls import reverse
from django.utils.text import slugify
from simple_history.models import HistoricalRecords


class Page(models.Model):
    title = models.CharField(
        max_length=200, help_text="Page title (shown in browser tab and as heading)"
    )
    slug = models.SlugField(
        unique=True,
        max_length=200,
        help_text="URL path (e.g., 'datasets' for /datasets/). Leave blank to auto-generate from title.",
    )
    content = models.TextField(
        help_text="Page content. HTML is allowed for formatting."
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
