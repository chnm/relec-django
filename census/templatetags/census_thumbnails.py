"""Template tags for displaying thumbnails without generating them.

The stock ``{% thumbnail %}`` tag generates missing thumbnails during
template rendering. With media on object storage that means downloading
the full archival scan, resizing it, and uploading the result — inside
the request. On cold-cache pages (e.g. crawler traffic) this blocks
requests long enough that Daphne kills the application instances and
the container healthcheck fails.

``{% existing_thumbnail_url %}`` only ever *looks up* a thumbnail
(two queries against easy-thumbnails' cache tables — no storage I/O).
Generation happens outside the request cycle: on upload via the
``saved_file`` signal (see ``census.apps``) and in bulk via the
``generate_thumbnails`` management command.
"""

import logging

from django import template
from easy_thumbnails.alias import aliases
from easy_thumbnails.files import get_thumbnailer

logger = logging.getLogger(__name__)

register = template.Library()


@register.simple_tag
def existing_thumbnail_url(fieldfile, alias):
    """Return the URL of an already-generated thumbnail, or "" if absent.

    Usage::

        {% existing_thumbnail_url record.original_image 'medium' as thumb_url %}
        {% if thumb_url %}<img src="{{ thumb_url }}">{% endif %}
    """
    if not fieldfile:
        return ""
    try:
        thumbnailer = get_thumbnailer(fieldfile)
        options = aliases.get(alias, target=thumbnailer.alias_target)
        if not options:
            logger.warning("Unknown thumbnail alias %r", alias)
            return ""
        thumbnail = thumbnailer.get_existing_thumbnail(options)
        return thumbnail.url if thumbnail else ""
    except Exception:
        logger.exception("Thumbnail lookup failed for %r", getattr(fieldfile, "name", fieldfile))
        return ""
