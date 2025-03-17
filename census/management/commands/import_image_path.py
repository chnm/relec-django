import csv

from django.core.management.base import BaseCommand
from django.db import transaction

from census.models import CensusSchedule


class Command(BaseCommand):
    help = "Update CensusSchedule records with additional metadata"

    def add_arguments(self, parser):
        parser.add_argument("csv_file", type=str, help="Path to the schedule CSV file")

    def handle(self, *args, **options):
        with open(options["csv_file"], "r") as file:
            reader = csv.DictReader(file)

            for row in reader:
                try:
                    with transaction.atomic():
                        self.stdout.write(f"\nProcessing row {row['resource_id']}")

                        # Find the existing record
                        schedule = CensusSchedule.objects.get(
                            resource_id=int(row["resource_id"])
                        )

                        # Clean and update values
                        schedule.box = row["box"]
                        schedule.notes = (
                            None if row["notes"] == "NULL" else row["notes"]
                        )
                        schedule.datascribe_original_image_path = row[
                            "image_original_path"
                        ]
                        schedule.omeka_storage_id = row["storage_id"]

                        schedule.save()

                        self.stdout.write(
                            self.style.SUCCESS(
                                f"Successfully updated schedule {row['resource_id']}"
                            )
                        )

                except CensusSchedule.DoesNotExist:
                    self.stdout.write(
                        self.style.WARNING(
                            f"Schedule {row['resource_id']} not found in database"
                        )
                    )
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(
                            f"Error processing row {row['resource_id']}: {str(e)}"
                        )
                    )
                    continue
