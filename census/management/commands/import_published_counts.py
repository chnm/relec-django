"""
Import published church counts from the 1926 Census Vol. 1 tables CSV.

Matches rows to Denomination records by denomination_id and sets
the published_churches_count field.

Usage:
    uv run python manage.py import_published_counts "1926 census vol 1 tables.csv"
"""

import csv

from django.core.management.base import BaseCommand

from census.models import Denomination


class Command(BaseCommand):
    help = "Import published church counts from 1926 Census Vol. 1 tables CSV"

    def add_arguments(self, parser):
        parser.add_argument("csv_file", help="Path to the CSV file")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be updated without saving",
        )

    def handle(self, *args, **options):
        csv_file = options["csv_file"]
        dry_run = options["dry_run"]

        updated = 0
        skipped = 0
        not_found = 0

        with open(csv_file, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                denom_id = row.get("denomination_id", "").strip()
                churches_total = row.get("churches_total", "").strip()
                denom_name = row.get("denomination_name", "").strip()

                if not denom_id or not churches_total:
                    skipped += 1
                    continue

                try:
                    count = int(churches_total.replace(",", ""))
                except ValueError:
                    self.stderr.write(
                        f"  Skipping {denom_name}: invalid count '{churches_total}'"
                    )
                    skipped += 1
                    continue

                try:
                    denom = Denomination.objects.get(denomination_id=denom_id)
                    if dry_run:
                        self.stdout.write(
                            f"  Would set {denom.name} ({denom_id}): {count}"
                        )
                    else:
                        denom.published_churches_count = count
                        denom.save(update_fields=["published_churches_count"])
                    updated += 1
                except Denomination.DoesNotExist:
                    self.stderr.write(
                        f"  Not found: {denom_name} ({denom_id})"
                    )
                    not_found += 1

        prefix = "[DRY RUN] " if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}Updated: {updated}, Skipped: {skipped}, Not found: {not_found}"
            )
        )
