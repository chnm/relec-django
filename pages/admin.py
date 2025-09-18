from django.contrib import admin
from django.utils.html import format_html
from simple_history.admin import SimpleHistoryAdmin

from .models import Page


@admin.register(Page)
class PageAdmin(SimpleHistoryAdmin):
    list_display = [
        "title",
        "slug",
        "is_published",
        "show_in_nav",
        "nav_order",
        "updated_at",
        "view_on_site_link",
    ]
    list_filter = ["is_published", "show_in_nav", "created_at", "updated_at"]
    search_fields = ["title", "slug", "content"]
    prepopulated_fields = {"slug": ("title",)}
    list_editable = ["is_published", "show_in_nav", "nav_order"]

    fieldsets = (
        ("Basic Information", {"fields": ("title", "slug", "content")}),
        ("SEO & Meta", {"fields": ("meta_description",), "classes": ("collapse",)}),
        (
            "Publishing",
            {"fields": ("is_published", "publish_date"), "classes": ("collapse",)},
        ),
        (
            "Navigation",
            {
                "fields": ("show_in_nav", "nav_title", "nav_order"),
                "classes": ("collapse",),
            },
        ),
    )

    # Show timestamps in readonly
    readonly_fields = ("created_at", "updated_at")

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)

        # Add timestamps section if editing existing object
        if obj:
            fieldsets = fieldsets + (
                (
                    "Timestamps",
                    {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
                ),
            )

        return fieldsets

    def view_on_site_link(self, obj):
        """Add a 'View on site' link in the admin list"""
        if obj.is_live:
            url = obj.get_absolute_url()
            return format_html('<a href="{}" target="_blank">View →</a>', url)
        return "Not live"

    view_on_site_link.short_description = "View on site"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related()

    # Custom admin actions
    actions = ["make_published", "make_unpublished", "add_to_nav", "remove_from_nav"]

    def make_published(self, request, queryset):
        count = queryset.update(is_published=True)
        self.message_user(request, f"{count} pages marked as published.")

    make_published.short_description = "Mark selected pages as published"

    def make_unpublished(self, request, queryset):
        count = queryset.update(is_published=False)
        self.message_user(request, f"{count} pages marked as unpublished.")

    make_unpublished.short_description = "Mark selected pages as unpublished"

    def add_to_nav(self, request, queryset):
        count = queryset.update(show_in_nav=True)
        self.message_user(request, f"{count} pages added to navigation.")

    add_to_nav.short_description = "Add selected pages to navigation"

    def remove_from_nav(self, request, queryset):
        count = queryset.update(show_in_nav=False)
        self.message_user(request, f"{count} pages removed from navigation.")

    remove_from_nav.short_description = "Remove selected pages from navigation"

    class Media:
        # Add custom CSS/JS if needed
        css = {"all": ()}
        js = ()
