"""
Link CensusSchedule records to Counties using Omeka API county data.

This command complements import_transcribed_locations.py by:
1. Fetching county (AHCB) codes from Omeka API for each schedule
2. Linking CensusSchedule records to County records
3. Helping with schedules that have unlisted populated places

Usage:
    python manage.py link_counties_from_omeka
    python manage.py link_counties_from_omeka --dry-run
    python manage.py link_counties_from_omeka --limit 10  # For testing
"""

import time

import requests
from django.core.management.base import BaseCommand
from django.db import transaction

from census.models import CensusSchedule, Denomination
from location.models import County


class Command(BaseCommand):
    help = "Link CensusSchedule records to Counties using Omeka API"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be updated without making changes",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Limit number of API pages to fetch (for testing)",
        )
        parser.add_argument(
            "--start-page",
            type=int,
            default=1,
            help="Start from specific page number (useful for resuming)",
        )
        parser.add_argument(
            "--only-missing",
            action="store_true",
            help="Only update schedules that don't have a county set",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        limit = options["limit"]
        start_page = options["start_page"]
        only_missing = options["only_missing"]

        if dry_run:
            self.stdout.write(
                self.style.WARNING("DRY RUN MODE - No changes will be saved")
            )

        if start_page > 1:
            self.stdout.write(self.style.SUCCESS(f"Resuming from page {start_page}"))

        if only_missing:
            self.stdout.write("Only updating schedules without counties")

        # Statistics
        stats = {
            "total_schedules_fetched": 0,
            "schedules_with_county": 0,
            "matched_to_census_schedule": 0,
            "matched_to_county": 0,
            "counties_linked": 0,
            "already_had_county": 0,
            "errors": 0,
        }

        # Fetch schedule items from Omeka API
        base_url = "https://omeka.religiousecologies.org/api/items"
        params = {
            "resource_class_id": 111,  # mare:Schedule resource class
            "per_page": 100,
            "page": start_page,
        }

        page_count = 0
        while True:
            if limit and page_count >= limit:
                self.stdout.write(f"Reached page limit of {limit}")
                break

            try:
                self.stdout.write(f"Fetching page {params['page']}...")
                response = requests.get(base_url, params=params, timeout=30)
                response.raise_for_status()
                items = response.json()

                if not items:
                    self.stdout.write("No more items found")
                    break

                stats["total_schedules_fetched"] += len(items)

                # Process each schedule item
                for item in items:
                    self.process_schedule_item(
                        item, stats, dry_run, only_missing=only_missing
                    )

                # Move to next page
                params["page"] += 1
                page_count += 1

                # Be nice to the API
                time.sleep(0.5)

            except requests.exceptions.RequestException as e:
                self.stdout.write(self.style.ERROR(f"API request failed: {e}"))
                stats["errors"] += 1
                break
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Unexpected error: {e}"))
                stats["errors"] += 1
                break

        # Print summary
        self.print_summary(stats, dry_run)

    def process_schedule_item(self, item, stats, dry_run, only_missing=False):
        """Process a single schedule item from Omeka API"""
        try:
            # Extract schedule_id, denomination_id, and ahcb_county_id
            schedule_id = self.get_omeka_value(item, "mare:scheduleId")
            denomination_id = self.get_omeka_value(item, "mare:denominationId")
            ahcb_county_id = self.get_omeka_value(item, "mare:ahcbCountyId")

            if not schedule_id or not denomination_id:
                return

            if ahcb_county_id:
                stats["schedules_with_county"] += 1

            # Match to Django Denomination first
            try:
                denomination = Denomination.objects.get(denomination_id=denomination_id)
            except Denomination.DoesNotExist:
                return
            except Denomination.MultipleObjectsReturned:
                self.stdout.write(
                    self.style.WARNING(
                        f"Multiple Denomination records for denomination_id {denomination_id}"
                    )
                )
                stats["errors"] += 1
                return

            # Match to Django CensusSchedule using schedule_id + denomination
            try:
                schedule_title = f"{denomination.name}: {schedule_id}"
                census_schedule = CensusSchedule.objects.get(
                    schedule_title=schedule_title
                )
                stats["matched_to_census_schedule"] += 1
            except CensusSchedule.DoesNotExist:
                return
            except CensusSchedule.MultipleObjectsReturned:
                self.stdout.write(
                    self.style.WARNING(
                        f"Multiple CensusSchedule records for {schedule_title}"
                    )
                )
                stats["errors"] += 1
                return

            # Check if we should skip (if only_missing and already has county)
            if only_missing and census_schedule.county:
                stats["already_had_county"] += 1
                return

            # Match to Django County by AHCB ID
            if ahcb_county_id:
                try:
                    county = County.objects.filter(ahcb_id=ahcb_county_id).first()
                    if county:
                        stats["matched_to_county"] += 1

                        # Update the CensusSchedule
                        if not dry_run:
                            with transaction.atomic():
                                census_schedule.county = county
                                census_schedule.save(update_fields=["county"])

                        stats["counties_linked"] += 1
                        self.stdout.write(
                            f"  Linked schedule {schedule_id} to {county}"
                        )
                    else:
                        self.stdout.write(
                            self.style.WARNING(
                                f"  County not found for AHCB ID: {ahcb_county_id}"
                            )
                        )
                except Exception as e:
                    self.stdout.write(
                        self.style.WARNING(
                            f"Error finding county for {ahcb_county_id}: {e}"
                        )
                    )

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"Error processing item {item.get('o:id')}: {e}")
            )
            stats["errors"] += 1

    def get_omeka_value(self, item, property_name):
        """Extract a literal value from Omeka API response"""
        values = item.get(property_name, [])
        if values and len(values) > 0:
            return values[0].get("@value")
        return None

    def print_summary(self, stats, dry_run):
        """Print summary statistics"""
        self.stdout.write("\n" + "=" * 70)
        self.stdout.write(self.style.SUCCESS("SUMMARY"))
        self.stdout.write("=" * 70)
        self.stdout.write(
            f"Total schedules fetched: {stats['total_schedules_fetched']}"
        )
        self.stdout.write(
            f"Schedules with county data: {stats['schedules_with_county']}"
        )
        self.stdout.write(
            f"Matched to CensusSchedule: {stats['matched_to_census_schedule']}"
        )
        self.stdout.write(f"Matched to County: {stats['matched_to_county']}")
        self.stdout.write(f"Counties linked: {stats['counties_linked']}")
        if stats["already_had_county"] > 0:
            self.stdout.write(f"Already had county: {stats['already_had_county']}")
        self.stdout.write(f"Errors: {stats['errors']}")

        if dry_run:
            self.stdout.write(
                self.style.WARNING("\nDRY RUN - No changes were actually saved")
            )
