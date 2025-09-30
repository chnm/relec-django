import csv
import os

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from census.models import Denomination


class Command(BaseCommand):
    help = "Import denominations from CSV file"

    def add_arguments(self, parser):
        parser.add_argument(
            "csv_file", type=str, help="Path to CSV file containing denomination data"
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=1000,
            help="Number of records to process in each batch (default: 1000)",
        )
        parser.add_argument(
            "--clear-existing",
            action="store_true",
            help="Clear all existing denominations before import",
        )

    def handle(self, *args, **options):
        csv_file = options["csv_file"]
        batch_size = options["batch_size"]
        clear_existing = options["clear_existing"]

        if not os.path.exists(csv_file):
            raise CommandError(f'File "{csv_file}" does not exist.')

        if clear_existing:
            self.stdout.write(self.style.WARNING("Clearing existing denominations..."))
            Denomination.objects.all().delete()
            self.stdout.write(self.style.SUCCESS("Existing denominations cleared."))

        created_count = 0
        updated_count = 0
        skipped_count = 0
        error_count = 0

        with open(csv_file, "r", encoding="utf-8") as file:
            reader = csv.DictReader(file)

            # Validate required columns
            required_fields = ["denomination_id", "name"]
            missing_fields = set(required_fields) - set(reader.fieldnames)
            if missing_fields:
                raise CommandError(
                    f"CSV missing required columns: {', '.join(missing_fields)}"
                )

            denominations_to_create = []
            denominations_to_update = []

            for row_num, row in enumerate(
                reader, start=2
            ):  # Start at 2 because row 1 is headers
                try:
                    # Skip rows with empty denomination_id or name
                    if not row["denomination_id"] or not row["name"]:
                        self.stdout.write(
                            self.style.WARNING(
                                f"Row {row_num}: Skipping - missing denomination_id or name"
                            )
                        )
                        skipped_count += 1
                        continue

                    # Check field lengths
                    if len(row["denomination_id"]) > 50:
                        self.stdout.write(
                            self.style.WARNING(
                                f"Row {row_num}: Skipping - denomination_id too long ({len(row['denomination_id'])} chars)"
                            )
                        )
                        skipped_count += 1
                        continue

                    if len(row["name"]) > 255:
                        self.stdout.write(
                            self.style.WARNING(
                                f"Row {row_num}: Skipping - name too long ({len(row['name'])} chars)"
                            )
                        )
                        skipped_count += 1
                        continue

                    # Handle optional fields with proper defaults
                    short_name = row.get("short_name", "").strip() or None
                    family_census = row.get("family_census", "").strip() or None
                    family_relec = row.get("family_relec", "").strip() or None

                    # Check if denomination exists
                    try:
                        denomination = Denomination.objects.get(
                            denomination_id=row["denomination_id"]
                        )
                        # Update existing
                        denomination.name = row["name"]
                        denomination.short_name = short_name
                        denomination.family_census = family_census
                        denomination.family_relec = family_relec
                        denominations_to_update.append(denomination)

                    except Denomination.DoesNotExist:
                        # Create new
                        denomination = Denomination(
                            denomination_id=row["denomination_id"],
                            name=row["name"],
                            short_name=short_name,
                            family_census=family_census,
                            family_relec=family_relec,
                        )
                        denominations_to_create.append(denomination)

                    # Process in batches
                    if (
                        len(denominations_to_create) + len(denominations_to_update)
                        >= batch_size
                    ):
                        with transaction.atomic():
                            if denominations_to_create:
                                Denomination.objects.bulk_create(
                                    denominations_to_create
                                )
                                created_count += len(denominations_to_create)
                                denominations_to_create = []

                            if denominations_to_update:
                                Denomination.objects.bulk_update(
                                    denominations_to_update,
                                    [
                                        "name",
                                        "short_name",
                                        "family_census",
                                        "family_relec",
                                    ],
                                )
                                updated_count += len(denominations_to_update)
                                denominations_to_update = []

                        self.stdout.write(
                            f"Processed {created_count + updated_count + skipped_count + error_count} rows..."
                        )

                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f"Row {row_num}: Error - {str(e)}")
                    )
                    error_count += 1

            # Process remaining records
            with transaction.atomic():
                if denominations_to_create:
                    Denomination.objects.bulk_create(denominations_to_create)
                    created_count += len(denominations_to_create)

                if denominations_to_update:
                    Denomination.objects.bulk_update(
                        denominations_to_update,
                        ["name", "short_name", "family_census", "family_relec"],
                    )
                    updated_count += len(denominations_to_update)

        self.stdout.write(
            self.style.SUCCESS(
                f"Import complete: {created_count} created, {updated_count} updated, "
                f"{skipped_count} skipped, {error_count} errors"
            )
        )
