"""
Management command to link ReligiousBody records to Locations using Omeka API data.

This command fetches schedule metadata from the Omeka API which contains AHCB county codes,
then matches those to Django Location records and updates ReligiousBody.location_id.
"""

import time

import requests
from django.core.management.base import BaseCommand
from django.db import transaction

from census.models import CensusSchedule, Denomination, ReligiousBody
from location.models import Location


class Command(BaseCommand):
    help = "Link ReligiousBody records to Locations using Omeka API county data"

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

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        limit = options["limit"]
        start_page = options["start_page"]

        if dry_run:
            self.stdout.write(
                self.style.WARNING("DRY RUN MODE - No changes will be saved")
            )

        if start_page > 1:
            self.stdout.write(self.style.SUCCESS(f"Resuming from page {start_page}"))

        # Statistics
        stats = {
            "total_schedules_fetched": 0,
            "schedules_with_county": 0,
            "matched_to_census_schedule": 0,
            "matched_to_location": 0,
            "updated_religious_bodies": 0,
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
                    self.process_schedule_item(item, stats, dry_run)

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
        self.stdout.write(f"Matched to Location: {stats['matched_to_location']}")
        self.stdout.write(
            f"ReligiousBody records updated: {stats['updated_religious_bodies']}"
        )
        self.stdout.write(f"Errors: {stats['errors']}")

        if dry_run:
            self.stdout.write(
                self.style.WARNING("\nDRY RUN - No changes were actually saved")
            )

    def process_schedule_item(self, item, stats, dry_run):
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
                # Denomination not in Django database
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
                # Try to match by schedule title (which includes denomination name)
                schedule_title = f"{denomination.name}: {schedule_id}"
                census_schedule = CensusSchedule.objects.get(
                    schedule_title=schedule_title
                )
                stats["matched_to_census_schedule"] += 1
            except CensusSchedule.DoesNotExist:
                # Schedule not in Django database
                return
            except CensusSchedule.MultipleObjectsReturned:
                self.stdout.write(
                    self.style.WARNING(
                        f"Multiple CensusSchedule records for {schedule_title}"
                    )
                )
                stats["errors"] += 1
                return

            # Match to Django Location by county_ahcb
            location = None
            if ahcb_county_id:
                try:
                    location = Location.objects.filter(
                        county_ahcb=ahcb_county_id
                    ).first()
                    if location:
                        stats["matched_to_location"] += 1
                except Exception as e:
                    self.stdout.write(
                        self.style.WARNING(
                            f"Error finding location for {ahcb_county_id}: {e}"
                        )
                    )

            # Update ReligiousBody records linked to this CensusSchedule
            if location:
                religious_bodies = ReligiousBody.objects.filter(
                    census_record=census_schedule, location__isnull=True
                )
                count = religious_bodies.count()

                if count > 0:
                    if not dry_run:
                        with transaction.atomic():
                            religious_bodies.update(location=location)
                    stats["updated_religious_bodies"] += count

                    if count == 1:
                        self.stdout.write(
                            f"  Updated 1 ReligiousBody for schedule {schedule_id} -> {location.city}, {location.state}"
                        )
                    else:
                        self.stdout.write(
                            f"  Updated {count} ReligiousBody records for schedule {schedule_id} -> {location.city}, {location.state}"
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
