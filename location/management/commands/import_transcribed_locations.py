"""
Link CensusSchedule records to existing location data from transcribed census data.

This command assumes State, County, and PopulatedPlace records already exist
(populated from the canonical data.chnm.org API via import_locations.py).

This command:
1. Reads schedules_with_datascribe.csv to find all transcribed locations
2. Links CensusSchedule records to existing County and PopulatedPlace records
3. Does NOT create or modify any location hierarchy records

Usage:
    python manage.py import_transcribed_locations --schedules static-data/schedules_with_datascribe.csv --places static-data/popplaces_1926.csv
"""

import csv

from django.core.management.base import BaseCommand

from census.models import CensusSchedule
from location.models import County, PopulatedPlace


class Command(BaseCommand):
    help = "Link CensusSchedule records to existing location data from transcribed census data"

    def add_arguments(self, parser):
        parser.add_argument(
            "--schedules",
            type=str,
            required=True,
            help="Path to schedules_with_datascribe.csv",
        )
        parser.add_argument(
            "--places", type=str, required=True, help="Path to popplaces_1926.csv"
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be linked without saving",
        )

    def handle(self, *args, **options):
        schedules_file = options["schedules"]
        places_file = options["places"]
        dry_run = options["dry_run"]

        if dry_run:
            self.stdout.write(
                self.style.WARNING("DRY RUN MODE - No changes will be saved")
            )

        stats = {
            "place_ids_found": set(),
            "unlisted_places_found": set(),
            "schedules_linked_by_place_id": 0,
            "schedules_unmatched_county": 0,
            "schedules_unmatched_place": 0,
            "schedules_linked_by_unlisted_name": 0,
            "schedules_no_location": 0,
        }

        # Step 1: Load all populated places from reference CSV
        self.stdout.write("\n=== Step 1: Loading populated places reference data ===")
        places_lookup = self.load_places_reference(places_file)
        self.stdout.write(
            self.style.SUCCESS(f"Loaded {len(places_lookup)} places from reference file")
        )

        # Step 2: Link CensusSchedule records to existing locations
        self.stdout.write("\n=== Step 2: Linking census schedules to locations ===")
        self.link_schedules_to_locations(schedules_file, places_lookup, stats, dry_run)

        self.print_summary(stats, dry_run)

    def load_places_reference(self, places_file):
        """Load the populated places reference CSV into a lookup dictionary"""
        places = {}
        with open(places_file, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                place_id = int(row["place_id"])
                places[place_id] = {
                    "name": row["place"],
                    "county_ahcb": row["county_ahcb"],
                }
        return places

    def link_schedules_to_locations(self, schedules_file, places_lookup, stats, dry_run):
        """
        Link CensusSchedule records to existing County and PopulatedPlace records.
        Does not create any new location records.
        """
        with open(schedules_file, "r") as f:
            reader = csv.DictReader(f)

            for row in reader:
                resource_id = int(row["resource_id"])
                place_id_str = row.get("(d, e, f) Location", "").strip()
                unlisted_place = row.get("(d) Unlisted Populated Place", "").strip()

                try:
                    schedule = CensusSchedule.objects.get(resource_id=resource_id)
                except CensusSchedule.DoesNotExist:
                    continue

                # Try to link by place_id first
                if place_id_str and place_id_str not in [
                    "NULL",
                    "MISSING",
                    "ILLEGIBLE",
                    "",
                ]:
                    try:
                        place_id = int(place_id_str)
                        stats["place_ids_found"].add(place_id)

                        if place_id in places_lookup:
                            place_data = places_lookup[place_id]
                            county = County.objects.filter(
                                ahcb_id=place_data["county_ahcb"]
                            ).first()
                            populated_place = PopulatedPlace.objects.filter(
                                place_id=place_id
                            ).first()

                            if not county:
                                stats["schedules_unmatched_county"] += 1
                                self.stdout.write(
                                    self.style.WARNING(
                                        f"  Schedule {resource_id}: no county found for AHCB ID '{place_data['county_ahcb']}' — run import_locations first"
                                    )
                                )
                                continue

                            if not populated_place:
                                stats["schedules_unmatched_place"] += 1

                            if not dry_run:
                                schedule.county = county
                                schedule.populated_place = populated_place
                                schedule.save(update_fields=["county", "populated_place"])

                            stats["schedules_linked_by_place_id"] += 1
                            continue
                    except (ValueError, KeyError):
                        pass

                # Track unlisted places (county linking handled by link_counties_from_omeka)
                if unlisted_place and unlisted_place not in [
                    "NULL",
                    "MISSING",
                    "ILLEGIBLE",
                    "",
                ]:
                    stats["unlisted_places_found"].add(unlisted_place)
                    stats["schedules_linked_by_unlisted_name"] += 1
                    continue

                stats["schedules_no_location"] += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Linked {stats['schedules_linked_by_place_id']} schedules by place_id"
            )
        )

    def print_summary(self, stats, dry_run):
        """Print linking summary"""
        self.stdout.write("\n" + "=" * 70)
        self.stdout.write(self.style.SUCCESS("SUMMARY"))
        self.stdout.write("=" * 70)
        self.stdout.write(
            f"Transcribed place IDs found: {len(stats['place_ids_found'])}"
        )
        self.stdout.write(
            f"Unlisted places found: {len(stats['unlisted_places_found'])}"
        )
        self.stdout.write(
            f"Schedules linked by place_id: {stats['schedules_linked_by_place_id']}"
        )
        if stats["schedules_unmatched_county"] > 0:
            self.stdout.write(
                self.style.WARNING(
                    f"Schedules with unmatched county (AHCB ID not in DB): {stats['schedules_unmatched_county']}"
                )
            )
        if stats["schedules_unmatched_place"] > 0:
            self.stdout.write(
                self.style.WARNING(
                    f"Schedules linked to county only (no PopulatedPlace match): {stats['schedules_unmatched_place']}"
                )
            )
        self.stdout.write(
            f"Schedules with unlisted places (use link_counties_from_omeka): {stats['schedules_linked_by_unlisted_name']}"
        )
        self.stdout.write(
            f"Schedules with no location: {stats['schedules_no_location']}"
        )

        if dry_run:
            self.stdout.write(
                self.style.WARNING("\nDRY RUN - No changes were actually saved")
            )
