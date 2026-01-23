from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import BlogPost, Visualization


@admin.register(BlogPost)
class BlogPostAdmin(ModelAdmin):
    list_display = ("title", "author", "published_date", "is_draft")
    list_filter = ("is_draft", "published_date", "author")
    search_fields = ("title", "content", "abstract")
    prepopulated_fields = {"slug": ("title",)}
    date_hierarchy = "published_date"
    ordering = ("-published_date",)


@admin.register(Visualization)
class VisualizationAdmin(ModelAdmin):
    list_display = ("title", "published_date", "updated_date", "doi")
    list_filter = ("published_date",)
    search_fields = ("title", "content", "abstract")
    prepopulated_fields = {"slug": ("title",)}
    date_hierarchy = "published_date"
    ordering = ("-published_date",)
