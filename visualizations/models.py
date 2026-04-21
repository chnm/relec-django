from django.db import models
from django.urls import reverse
from simple_history.models import HistoricalRecords


class Visualization(models.Model):
    """
    Consolidated visualization model. Handles three rendering paths:

    - "model": Markdown content rendered by VisualizationDetailView (e.g., catholic-dioceses)
    - "custom": Custom view function with its own template (e.g., denomination-map, urban-congregations)
    - "datalayer": Data layer map populated from DataLayer points (e.g., dc-churches, spiritualist-pastors)
    """

    RENDER_TYPE_CHOICES = [
        ("model", "Model-backed (Markdown + optional JS)"),
        ("custom", "Custom view (census maps, etc.)"),
        ("datalayer", "Data layer map"),
    ]

    title = models.CharField(max_length=500)
    slug = models.SlugField(max_length=200, unique=True)
    author = models.CharField(max_length=200, blank=True, help_text="Author(s) of the visualization")
    published_date = models.DateTimeField()
    updated_date = models.DateTimeField(blank=True, null=True)
    content = models.TextField(blank=True, help_text="Markdown content displayed below visualization")
    abstract = models.TextField(blank=True)
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

    # Rendering
    render_type = models.CharField(
        max_length=50,
        choices=RENDER_TYPE_CHOICES,
        default="model",
        help_text="How this visualization is rendered",
    )
    # For datalayer render_type: the DataLayer.source slug to query
    datalayer_source = models.CharField(
        max_length=255,
        blank=True,
        help_text="For datalayer type: the DataLayer source slug (e.g., 'dc-churches')",
    )
    # For custom render_type: the URL name to route to
    custom_view_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="For custom type: the Django URL name (e.g., 'denomination_map')",
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
        if self.thumbnail_image:
            return self.thumbnail_image.url
        return None
