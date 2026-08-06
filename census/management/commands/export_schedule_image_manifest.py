import csv
import os
import tempfile
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from census.models import CensusSchedule


class Command(BaseCommand):
    help = (
        "Export stable census resource IDs and their existing object-storage "
        "image keys without downloading image data"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "output",
            type=Path,
            help="Destination CSV path",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Export at most this many image mappings",
        )
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help="Replace an existing destination file",
        )

    def handle(self, *args, **options):
        output = options["output"]
        limit = options["limit"]
        overwrite = options["overwrite"]

        if limit is not None and limit < 1:
            raise CommandError("--limit must be at least 1.")
        if output.exists() and not overwrite:
            raise CommandError(
                f"Destination already exists: {output}. Use --overwrite to replace it."
            )
        if not output.parent.is_dir():
            raise CommandError(f"Destination directory does not exist: {output.parent}")

        queryset = (
            CensusSchedule.objects.exclude(original_image="")
            .exclude(original_image__isnull=True)
            .order_by("resource_id")
            .values_list("resource_id", "original_image")
        )
        if limit is not None:
            queryset = queryset[:limit]

        temporary_path = None
        exported = 0
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="",
                dir=output.parent,
                prefix=f".{output.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                writer = csv.writer(temporary_file)
                writer.writerow(["resource_id", "original_image"])
                for resource_id, original_image in queryset.iterator():
                    writer.writerow([resource_id, original_image])
                    exported += 1

            os.replace(temporary_path, output)
            temporary_path = None
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

        self.stdout.write(
            self.style.SUCCESS(
                f"Exported {exported} schedule image mappings to {output}."
            )
        )
