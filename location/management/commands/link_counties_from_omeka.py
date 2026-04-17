"""
Link CensusSchedule records to Counties using Omeka API county data.

This command complements import_transcribed_locations.py by:
1. Fetching county (AHCB) codes from Omeka API for each schedule
2. Linking CensusSchedule records to County records
3. Helping with schedules that have unlisted populated places

Usage:
    python manage.py link_counties_from_omeka
    python manage.py link_counties_from_omeka --dry-run
    python manage.py link_counties_from_omeka --load-cache reports/omeka_chnm_cache.json
    python manage.py link_counties_from_omeka --only-missing
    python manage.py link_counties_from_omeka --limit 10  # For testing
"""

import json
import time
from pathlib import Path

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
            "--load-cache",
            type=str,
            default=None,
            metavar="FILE",
            help="Load Omeka data from a cache JSON file (e.g. from data_reconciliation --save-cache) instead of fetching from the API",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Limit number of API pages to fetch (for testing; ignored with --load-cache)",
        )
        parser.add_argument(
            "--start-page",
            type=int,
            default=1,
            help="Start from specific page number (useful for resuming; ignored with --load-cache)",
        )
        parser.add_argument(
            "--only-missing",
            action="store_true",
            help="Only update schedules that don't have a county set",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        only_missing = options["only_missing"]
        cache_file = options.get("load_cache")

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN MODE - No changes will be saved"))
        if only_missing:
            self.stdout.write("Only updating schedules without counties")

        # Pre-load county lookup and schedule lookup into memory for bulk efficiency
        self.stdout.write("Pre-loading County and CensusSchedule data ...")
        self.county_by_ahcb = {c.ahcb_id: c for c in County.objects.all()}
        self.schedule_by_resource_id = {
            s.resource_id: s
            for s in CensusSchedule.objects.select_related("county").only(
                "id", "resource_id", "county_id"
            )
        }
        self.stdout.write(
            f"  {len(self.county_by_ahcb):,} counties, "
            f"{len(self.schedule_by_resource_id):,} schedules loaded"
        )

        stats = {
            "total_schedules_fetched": 0,
            "schedules_with_county": 0,
            "matched_to_census_schedule": 0,
            "matched_to_county": 0,
            "counties_linked": 0,
            "already_had_county": 0,
            "county_not_found": 0,
            "errors": 0,
        }

        if cache_file:
            self._link_from_cache(cache_file, stats, dry_run, only_missing)
        else:
            self._link_from_api(options, stats, dry_run, only_missing)

        self.print_summary(stats, dry_run)

    # ─────────────────────────────────────────────────────────────────────────
    # Cache-based path (fast)
    # ─────────────────────────────────────────────────────────────────────────

    def _link_from_cache(self, cache_file, stats, dry_run, only_missing):
        """Link counties using pre-fetched Omeka data from a cache JSON file."""
        cache_path = Path(cache_file)
        self.stdout.write(self.style.WARNING(f"Loading cache from {cache_path} ..."))
        with open(cache_path) as fh:
            cached = json.load(fh)

        omeka_schedules = cached["omeka_schedules"]
        self.stdout.write(f"  {len(omeka_schedules):,} Omeka schedule items in cache")

        # Collect updates in bulk
        to_update = []
        skipped_no_county = 0

        for item in omeka_schedules:
            stats["total_schedules_fetched"] += 1
            omeka_id = item.get("omeka_id")
            ahcb_county_id = item.get("ahcb_county_id")

            if ahcb_county_id:
                stats["schedules_with_county"] += 1
            else:
                skipped_no_county += 1
                continue

            # Match to CensusSchedule by resource_id (direct, reliable)
            schedule = self.schedule_by_resource_id.get(omeka_id)
            if not schedule:
                continue
            stats["matched_to_census_schedule"] += 1

            # Skip if already has county and --only-missing
            if only_missing and schedule.county_id:
                stats["already_had_county"] += 1
                continue

            # Match county
            county = self.county_by_ahcb.get(ahcb_county_id)
            if not county:
                stats["county_not_found"] += 1
                continue
            stats["matched_to_county"] += 1

            # Skip if county is already correct
            if schedule.county_id == county.id:
                stats["already_had_county"] += 1
                continue

            schedule.county = county
            to_update.append(schedule)
            stats["counties_linked"] += 1

        self.stdout.write(
            f"  {skipped_no_county:,} schedules had no county in Omeka (skipped)"
        )
        self.stdout.write(f"  {len(to_update):,} schedules to update")

        if not dry_run and to_update:
            self.stdout.write("  Writing updates ...")
            with transaction.atomic():
                CensusSchedule.objects.bulk_update(to_update, ["county"], batch_size=500)
            self.stdout.write(self.style.SUCCESS(f"  Done — {len(to_update):,} records updated"))

    # ─────────────────────────────────────────────────────────────────────────
    # API-based path (original behaviour)
    # ─────────────────────────────────────────────────────────────────────────

    def _link_from_api(self, options, stats, dry_run, only_missing):
        """Link counties by paging through the Omeka API."""
        limit = options["limit"]
        start_page = options["start_page"]

        if start_page > 1:
            self.stdout.write(self.style.SUCCESS(f"Resuming from page {start_page}"))

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

                for item in items:
                    self._process_api_item(item, stats, dry_run, only_missing)

                params["page"] += 1
                page_count += 1
                time.sleep(0.5)

            except requests.exceptions.RequestException as e:
                self.stdout.write(self.style.ERROR(f"API request failed: {e}"))
                stats["errors"] += 1
                break
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Unexpected error: {e}"))
                stats["errors"] += 1
                break

    def _process_api_item(self, item, stats, dry_run, only_missing):
        """Process a single raw Omeka API item."""
        try:
            omeka_id = item.get("o:id")
            ahcb_county_id = self._get_omeka_value(item, "mare:ahcbCountyId")

            if ahcb_county_id:
                stats["schedules_with_county"] += 1

            # Match to CensusSchedule by resource_id
            schedule = self.schedule_by_resource_id.get(omeka_id)
            if not schedule:
                # Fallback: match by schedule_title (legacy behaviour)
                schedule_id = self._get_omeka_value(item, "mare:scheduleId")
                denomination_id = self._get_omeka_value(item, "mare:denominationId")
                if not schedule_id or not denomination_id:
                    return
                try:
                    denomination = Denomination.objects.get(denomination_id=denomination_id)
                    schedule_title = f"{denomination.name}: {schedule_id}"
                    schedule = CensusSchedule.objects.get(schedule_title=schedule_title)
                except (Denomination.DoesNotExist, CensusSchedule.DoesNotExist,
                        CensusSchedule.MultipleObjectsReturned):
                    return
            stats["matched_to_census_schedule"] += 1

            if only_missing and schedule.county_id:
                stats["already_had_county"] += 1
                return

            if not ahcb_county_id:
                return

            county = self.county_by_ahcb.get(ahcb_county_id)
            if not county:
                stats["county_not_found"] += 1
                self.stdout.write(
                    self.style.WARNING(f"  County not found for AHCB ID: {ahcb_county_id}")
                )
                return
            stats["matched_to_county"] += 1

            if schedule.county_id == county.id:
                stats["already_had_county"] += 1
                return

            if not dry_run:
                with transaction.atomic():
                    schedule.county = county
                    schedule.save(update_fields=["county"])

            stats["counties_linked"] += 1

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"Error processing item {item.get('o:id')}: {e}")
            )
            stats["errors"] += 1

    def _get_omeka_value(self, item, property_name):
        """Extract a literal value from a raw Omeka API response item."""
        values = item.get(property_name, [])
        return values[0].get("@value") if values else None

    def print_summary(self, stats, dry_run):
        self.stdout.write("\n" + "=" * 70)
        self.stdout.write(self.style.SUCCESS("SUMMARY"))
        self.stdout.write("=" * 70)
        self.stdout.write(f"Total schedules fetched:      {stats['total_schedules_fetched']:,}")
        self.stdout.write(f"Schedules with county data:   {stats['schedules_with_county']:,}")
        self.stdout.write(f"Matched to CensusSchedule:    {stats['matched_to_census_schedule']:,}")
        self.stdout.write(f"Matched to County:            {stats['matched_to_county']:,}")
        self.stdout.write(f"Counties linked:              {stats['counties_linked']:,}")
        if stats["already_had_county"] > 0:
            self.stdout.write(f"Already had county (skipped): {stats['already_had_county']:,}")
        if stats["county_not_found"] > 0:
            self.stdout.write(
                self.style.WARNING(f"County AHCB ID not found:     {stats['county_not_found']:,}")
            )
        self.stdout.write(f"Errors:                       {stats['errors']:,}")
        if dry_run:
            self.stdout.write(self.style.WARNING("\nDRY RUN - No changes were actually saved"))
