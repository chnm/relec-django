import csv
from collections import Counter
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from census.models import CensusSchedule


IMAGE_KEY_PREFIX = "census_images/originals/"
REQUIRED_COLUMNS = {"resource_id", "original_image"}


def object_key_error(object_key):
    parsed = urlsplit(object_key)
    path = PurePosixPath(object_key)
    if not object_key:
        return "original_image is blank."
    if parsed.scheme or parsed.netloc:
        return "original_image must be an object key, not a URL."
    if "\\" in object_key or path.is_absolute() or ".." in path.parts:
        return "original_image contains an unsafe path."
    if not object_key.startswith(IMAGE_KEY_PREFIX):
        return f"original_image must begin with {IMAGE_KEY_PREFIX!r}."
    if object_key == IMAGE_KEY_PREFIX or path.name in {"", "."}:
        return "original_image must identify a file."
    return None


class Command(BaseCommand):
    help = (
        "Link CensusSchedule.original_image to existing object-storage keys from "
        "a resource_id manifest without uploading or downloading images"
    )

    def add_arguments(self, parser):
        parser.add_argument("manifest", type=Path, help="Image manifest CSV path")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate and report links without changing the database",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Process at most this many manifest rows",
        )
        parser.add_argument(
            "--verify-storage",
            action="store_true",
            help=(
                "Require every object key to exist in configured storage before "
                "linking"
            ),
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=500,
            help="Database batch size (default: 500)",
        )

    def handle(self, *args, **options):
        manifest = options["manifest"]
        dry_run = options["dry_run"]
        limit = options["limit"]
        verify_storage = options["verify_storage"]
        batch_size = options["batch_size"]

        if limit is not None and limit < 1:
            raise CommandError("--limit must be at least 1.")
        if batch_size < 1:
            raise CommandError("--batch-size must be at least 1.")
        if not manifest.is_file():
            raise CommandError(f"Manifest does not exist: {manifest}")

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — no database changes"))

        counts = Counter()
        seen = {}
        pending = []

        with manifest.open("r", encoding="utf-8-sig", newline="") as manifest_file:
            reader = csv.DictReader(manifest_file)
            self._validate_headers(reader.fieldnames)

            for line_number, row in enumerate(reader, start=2):
                if limit is not None and counts["rows"] >= limit:
                    break
                counts["rows"] += 1

                parsed = self._parse_row(row, line_number, counts)
                if parsed is None:
                    continue
                resource_id, object_key = parsed

                previous_key = seen.get(resource_id)
                if previous_key is not None:
                    if previous_key == object_key:
                        counts["duplicates"] += 1
                    else:
                        counts["invalid"] += 1
                        self.stderr.write(
                            f"Line {line_number}: resource_id {resource_id} has "
                            "conflicting object keys in the manifest."
                        )
                    continue
                seen[resource_id] = object_key
                pending.append((resource_id, object_key))

                if len(pending) >= batch_size:
                    self._process_batch(
                        pending,
                        counts,
                        dry_run=dry_run,
                        verify_storage=verify_storage,
                        batch_size=batch_size,
                    )
                    pending.clear()

        if pending:
            self._process_batch(
                pending,
                counts,
                dry_run=dry_run,
                verify_storage=verify_storage,
                batch_size=batch_size,
            )

        self._write_summary(counts, dry_run=dry_run)

        fatal_errors = (
            counts["invalid"]
            + counts["conflicts"]
            + counts["missing_objects"]
            + counts["storage_errors"]
        )
        if fatal_errors:
            raise CommandError(
                f"Manifest import completed with {fatal_errors} blocking error(s); "
                "affected rows were not linked."
            )

    def _validate_headers(self, fieldnames):
        if fieldnames is None:
            raise CommandError("Manifest is empty or has no CSV header.")
        missing = REQUIRED_COLUMNS.difference(fieldnames)
        if missing:
            raise CommandError(
                "Manifest is missing required column(s): " + ", ".join(sorted(missing))
            )

    def _parse_row(self, row, line_number, counts):
        raw_resource_id = (row.get("resource_id") or "").strip()
        object_key = (row.get("original_image") or "").strip()

        try:
            resource_id = int(raw_resource_id)
            if resource_id < 1:
                raise ValueError
        except ValueError:
            counts["invalid"] += 1
            self.stderr.write(
                f"Line {line_number}: invalid resource_id {raw_resource_id!r}."
            )
            return None

        error = object_key_error(object_key)
        if error:
            counts["invalid"] += 1
            self.stderr.write(f"Line {line_number}: {error}")
            return None

        return resource_id, object_key

    def _process_batch(
        self,
        mappings,
        counts,
        *,
        dry_run,
        verify_storage,
        batch_size,
    ):
        resource_ids = [resource_id for resource_id, _ in mappings]
        schedules = {
            schedule.resource_id: schedule
            for schedule in CensusSchedule.objects.filter(
                resource_id__in=resource_ids
            ).only("id", "resource_id", "original_image")
        }
        updates = []

        for resource_id, object_key in mappings:
            schedule = schedules.get(resource_id)
            if schedule is None:
                counts["missing_schedules"] += 1
                self.stderr.write(
                    f"No local CensusSchedule has resource_id {resource_id}; skipped."
                )
                continue

            current_key = (
                schedule.original_image.name if schedule.original_image else ""
            )
            if current_key:
                if current_key == object_key:
                    counts["already_linked"] += 1
                else:
                    counts["conflicts"] += 1
                    self.stderr.write(
                        f"Schedule {resource_id} already links to a different image; "
                        "skipped."
                    )
                continue

            if verify_storage and not self._object_exists(object_key, counts):
                continue

            if dry_run:
                counts["would_link"] += 1
                continue

            schedule.original_image = object_key
            updates.append(schedule)

        if updates:
            with transaction.atomic():
                CensusSchedule.objects.bulk_update(
                    updates,
                    ["original_image"],
                    batch_size=batch_size,
                )
            counts["linked"] += len(updates)

    def _object_exists(self, object_key, counts):
        try:
            exists = default_storage.exists(object_key)
        except Exception as exc:
            counts["storage_errors"] += 1
            self.stderr.write(
                f"Storage check failed for {object_key!r} ({type(exc).__name__}); "
                "skipped."
            )
            return False
        if not exists:
            counts["missing_objects"] += 1
            self.stderr.write(f"Object does not exist: {object_key!r}; skipped.")
            return False
        counts["verified_objects"] += 1
        return True

    def _write_summary(self, counts, *, dry_run):
        self.stdout.write(self.style.SUCCESS("\nSummary:"))
        self.stdout.write(f"  Manifest rows processed: {counts['rows']}")
        self.stdout.write(f"  Images linked: {counts['linked']}")
        if dry_run:
            self.stdout.write(f"  Images that would be linked: {counts['would_link']}")
        self.stdout.write(f"  Already linked: {counts['already_linked']}")
        self.stdout.write(f"  Missing local schedules: {counts['missing_schedules']}")
        self.stdout.write(f"  Conflicting existing links: {counts['conflicts']}")
        self.stdout.write(f"  Duplicate manifest rows: {counts['duplicates']}")
        self.stdout.write(f"  Invalid manifest rows: {counts['invalid']}")
        self.stdout.write(f"  Verified storage objects: {counts['verified_objects']}")
        self.stdout.write(f"  Missing storage objects: {counts['missing_objects']}")
        self.stdout.write(f"  Storage check errors: {counts['storage_errors']}")
