"""
Template filters for rendering Markdown content.
"""

import markdown as md
from django import template
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter(name="markdown")
def markdown_filter(text):
    """
    Convert Markdown text to HTML.

    Usage:
        {{ page.content|markdown }}
    """
    if not text:
        return ""

    # Configure markdown with common extensions
    extensions = [
        "markdown.extensions.extra",  # Includes tables, fenced code blocks, etc.
        "markdown.extensions.codehilite",  # Syntax highlighting for code blocks
        "markdown.extensions.nl2br",  # Convert newlines to <br> tags
        "markdown.extensions.sane_lists",  # Better list handling
        "markdown.extensions.smarty",  # Smart quotes and dashes
        "markdown.extensions.toc",  # Table of contents
    ]

    html = md.markdown(text, extensions=extensions)
    return mark_safe(html)
