"""
Clear county and populated_place foreign keys from CensusSchedule records.

This prepares schedules for re-linking with correct transcribed location data.
Location records (State, County, PopulatedPlace) are preserved.

Usage:
    python manage.py clear_schedule_locations --populated-places-only
    python manage.py clear_schedule_locations --all
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from census.models import CensusSchedule


class Command(BaseCommand):
    help = "Clear location foreign keys from CensusSchedule records"

    def add_arguments(self, parser):
        parser.add_argument(
            "--populated-places-only",
            action="store_true",
            help="Clear only populated_place, keep county",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="Clear both county and populated_place",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be cleared without making changes",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        populated_places_only = options["populated_places_only"]
        clear_all = options["all"]

        if not populated_places_only and not clear_all:
            self.stdout.write(
                self.style.ERROR(
                    "Must specify either --populated-places-only or --all"
                )
            )
            return

        if dry_run:
            self.stdout.write(
                self.style.WARNING("DRY RUN MODE - No changes will be saved")
            )

        # Count current relationships
        with_county = CensusSchedule.objects.filter(county__isnull=False).count()
        with_place = CensusSchedule.objects.filter(
            populated_place__isnull=False
        ).count()
        total = CensusSchedule.objects.count()

        self.stdout.write(f"\nCurrent state:")
        self.stdout.write(f"  Total schedules: {total}")
        self.stdout.write(f"  With county: {with_county}")
        self.stdout.write(f"  With populated_place: {with_place}")

        # Clear the relationships
        if not dry_run:
            with transaction.atomic():
                if clear_all:
                    self.stdout.write("\nClearing both county and populated_place...")
                    CensusSchedule.objects.update(county=None, populated_place=None)
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Cleared county and populated_place from {total} schedules"
                        )
                    )
                elif populated_places_only:
                    self.stdout.write("\nClearing populated_place only...")
                    CensusSchedule.objects.update(populated_place=None)
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Cleared populated_place from {total} schedules (kept county)"
                        )
                    )
        else:
            if clear_all:
                self.stdout.write(
                    f"\nWould clear county and populated_place from {total} schedules"
                )
            elif populated_places_only:
                self.stdout.write(
                    f"\nWould clear populated_place from {total} schedules (keep county)"
                )

        # Show final state (if not dry run)
        if not dry_run:
            with_county_after = CensusSchedule.objects.filter(
                county__isnull=False
            ).count()
            with_place_after = CensusSchedule.objects.filter(
                populated_place__isnull=False
            ).count()

            self.stdout.write(f"\nFinal state:")
            self.stdout.write(f"  With county: {with_county_after}")
            self.stdout.write(f"  With populated_place: {with_place_after}")
