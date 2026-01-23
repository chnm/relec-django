import csv
import os

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from location.models import Location


class Command(BaseCommand):
    help = "Import locations from CSV file"

    def add_arguments(self, parser):
        parser.add_argument(
            "csv_file", type=str, help="Path to CSV file containing location data"
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
            help="Clear all existing locations before import",
        )

    def handle(self, *args, **options):
        csv_file = options["csv_file"]
        batch_size = options["batch_size"]
        clear_existing = options["clear_existing"]

        if not os.path.exists(csv_file):
            raise CommandError(f'File "{csv_file}" does not exist.')

        if clear_existing:
            self.stdout.write(self.style.WARNING("Clearing existing locations..."))
            Location.objects.all().delete()
            self.stdout.write(self.style.SUCCESS("Existing locations cleared."))

        created_count = 0
        updated_count = 0
        skipped_count = 0
        error_count = 0

        with open(csv_file, "r", encoding="utf-8") as file:
            reader = csv.DictReader(file)

            # Validate required columns (handle 'place' vs 'city')
            expected_fieldnames = set(reader.fieldnames)
            required_fields = [
                "place_id",
                "county",
                "state",
                "map_name",
                "county_ahcb",
                "lat",
                "lon",
            ]

            # Check for either 'city' or 'place' column
            if "city" not in expected_fieldnames and "place" not in expected_fieldnames:
                raise CommandError('CSV missing required column: "city" or "place"')

            city_field = "city" if "city" in expected_fieldnames else "place"

            missing_fields = set(required_fields) - expected_fieldnames
            if missing_fields:
                raise CommandError(
                    f"CSV missing required columns: {', '.join(missing_fields)}"
                )

            locations_to_create = []
            locations_to_update = []

            for row_num, row in enumerate(
                reader, start=2
            ):  # Start at 2 because row 1 is headers
                try:
                    # Validate required fields are not empty
                    if not row["place_id"] or not row["place_id"].strip():
                        self.stdout.write(
                            self.style.WARNING(
                                f"Row {row_num}: Skipping - place_id is empty"
                            )
                        )
                        skipped_count += 1
                        continue

                    # Check field lengths
                    city_value = row[city_field]
                    if len(city_value) > 250:
                        self.stdout.write(
                            self.style.WARNING(
                                f"Row {row_num}: Skipping - city name too long ({len(city_value)} chars)"
                            )
                        )
                        skipped_count += 1
                        continue

                    # Convert and validate numeric fields
                    try:
                        place_id = int(row["place_id"])
                        lat = float(row["lat"])
                        lon = float(row["lon"])
                    except (ValueError, TypeError):
                        self.stdout.write(
                            self.style.WARNING(
                                f"Row {row_num}: Skipping - invalid numeric values"
                            )
                        )
                        skipped_count += 1
                        continue

                    # Check if location exists
                    try:
                        location = Location.objects.get(place_id=place_id)
                        # Update existing
                        location.city = city_value
                        location.county = row["county"]
                        location.state = row["state"]
                        location.map_name = row["map_name"]
                        location.county_ahcb = row["county_ahcb"]
                        location.lat = lat
                        location.lon = lon
                        locations_to_update.append(location)

                    except Location.DoesNotExist:
                        # Create new
                        location = Location(
                            place_id=place_id,
                            city=city_value,
                            county=row["county"],
                            state=row["state"],
                            map_name=row["map_name"],
                            county_ahcb=row["county_ahcb"],
                            lat=lat,
                            lon=lon,
                        )
                        locations_to_create.append(location)

                    # Process in batches
                    if (
                        len(locations_to_create) + len(locations_to_update)
                        >= batch_size
                    ):
                        with transaction.atomic():
                            if locations_to_create:
                                Location.objects.bulk_create(locations_to_create)
                                created_count += len(locations_to_create)
                                locations_to_create = []

                            if locations_to_update:
                                Location.objects.bulk_update(
                                    locations_to_update,
                                    [
                                        "city",
                                        "county",
                                        "state",
                                        "map_name",
                                        "county_ahcb",
                                        "lat",
                                        "lon",
                                    ],
                                )
                                updated_count += len(locations_to_update)
                                locations_to_update = []

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
                if locations_to_create:
                    Location.objects.bulk_create(locations_to_create)
                    created_count += len(locations_to_create)

                if locations_to_update:
                    Location.objects.bulk_update(
                        locations_to_update,
                        [
                            "city",
                            "county",
                            "state",
                            "map_name",
                            "county_ahcb",
                            "lat",
                            "lon",
                        ],
                    )
                    updated_count += len(locations_to_update)

        self.stdout.write(
            self.style.SUCCESS(
                f"Import complete: {created_count} created, {updated_count} updated, "
                f"{skipped_count} skipped, {error_count} errors"
            )
        )
