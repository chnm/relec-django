"""Pre-generate thumbnail aliases for uploaded images.

Thumbnails must never be generated during a request (each miss means
downloading the original scan from object storage, resizing it, and
uploading the result — see census/templatetags/census_thumbnails.py).
Uploads through the admin or a form are covered by the ``saved_file``
signal in ``census.apps``. Run this command ad-hoc, not on deploys:
once as the initial backfill, and again after any bulk import that
attaches images without passing a file through Django's upload
machinery (e.g. writing object-storage paths straight into the DB —
the signal does not fire for those).

It is idempotent: already-generated thumbnails are skipped via
easy-thumbnails' cache tables without touching storage. Missing ones
require downloading the original from storage, so run it close to the
object store and use --limit to chunk large backfills.

    uv run python manage.py generate_thumbnails
"""

from django.core.management.base import BaseCommand
from easy_thumbnails.files import generate_all_aliases

from census.models import CensusSchedule
from pages.models import BlogPost
from visualizations.models import Visualization

# (model, image field name) pairs to backfill
IMAGE_FIELDS = [
    (CensusSchedule, "original_image"),
    (BlogPost, "thumbnail_image"),
    (Visualization, "thumbnail_image"),
]


class Command(BaseCommand):
    help = "Pre-generate all thumbnail aliases for uploaded images"

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Stop after this many images (across all models)",
        )

    def handle(self, *args, **options):
        limit = options["limit"]
        processed = failed = 0

        for model, field_name in IMAGE_FIELDS:
            queryset = (
                model.objects.exclude(**{field_name: ""})
                .exclude(**{f"{field_name}__isnull": True})
                .only("pk", field_name)
            )
            label = f"{model._meta.label}.{field_name}"
            self.stdout.write(f"{label}: {queryset.count()} images")

            for instance in queryset.iterator(chunk_size=500):
                if limit is not None and processed >= limit:
                    self.stdout.write(f"Reached --limit {limit}, stopping.")
                    self._summary(processed, failed)
                    return
                fieldfile = getattr(instance, field_name)
                try:
                    generate_all_aliases(fieldfile, include_global=True)
                except Exception as exc:
                    failed += 1
                    self.stderr.write(
                        f"  FAILED {label} pk={instance.pk} ({fieldfile.name}): {exc}"
                    )
                processed += 1
                if processed % 100 == 0:
                    self.stdout.write(f"  ...{processed} processed")

        self._summary(processed, failed)

    def _summary(self, processed, failed):
        style = self.style.WARNING if failed else self.style.SUCCESS
        self.stdout.write(style(f"Done: {processed} processed, {failed} failed"))
