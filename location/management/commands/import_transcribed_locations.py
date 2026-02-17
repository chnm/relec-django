"""
Import locations ONLY from transcribed census data.

This command:
1. Reads schedules_with_datascribe.csv to find all transcribed locations
2. Imports States, Counties, and PopulatedPlaces referenced in transcriptions
3. Links CensusSchedule records to their transcribed locations
4. Does NOT geocode or auto-generate locations

Usage:
    python manage.py import_transcribed_locations --schedules static-data/schedules_with_datascribe.csv --places static-data/popplaces_1926.csv
"""

import csv
from collections import defaultdict

from django.core.management.base import BaseCommand

from census.models import CensusSchedule
from location.models import County, PopulatedPlace, State


class Command(BaseCommand):
    help = "Import locations from transcribed census data only (no geocoding)"

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
            "--reset",
            action="store_true",
            help="Delete existing location data before import",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be imported without saving",
        )

    def handle(self, *args, **options):
        schedules_file = options["schedules"]
        places_file = options["places"]
        reset = options["reset"]
        dry_run = options["dry_run"]

        if dry_run:
            self.stdout.write(
                self.style.WARNING("DRY RUN MODE - No changes will be saved")
            )

        if reset and not dry_run:
            self.stdout.write("Resetting location data...")
            PopulatedPlace.objects.all().delete()
            County.objects.all().delete()
            State.objects.all().delete()
            self.stdout.write(self.style.SUCCESS("Location data reset complete"))

        # Statistics
        stats = {
            "place_ids_found": set(),
            "unlisted_places_found": set(),
            "states_created": 0,
            "counties_created": 0,
            "places_created": 0,
            "schedules_linked_by_place_id": 0,
            "schedules_linked_by_unlisted_name": 0,
            "schedules_no_location": 0,
        }

        # Step 1: Load all populated places from reference CSV
        self.stdout.write("\n=== Step 1: Loading populated places reference data ===")
        places_lookup = self.load_places_reference(places_file)
        self.stdout.write(
            self.style.SUCCESS(f"Loaded {len(places_lookup)} places from reference file")
        )

        # Step 2: Scan schedules CSV to find which places were actually transcribed
        self.stdout.write("\n=== Step 2: Scanning transcribed data ===")
        transcribed_data = self.scan_transcribed_locations(schedules_file, stats)
        self.stdout.write(
            self.style.SUCCESS(
                f"Found {len(stats['place_ids_found'])} place IDs and {len(stats['unlisted_places_found'])} unlisted places"
            )
        )

        # Step 3: Import only the transcribed locations
        self.stdout.write("\n=== Step 3: Importing transcribed locations ===")
        if not dry_run:
            self.import_locations(places_lookup, stats, transcribed_data)

        # Step 4: Link CensusSchedule records to locations
        self.stdout.write("\n=== Step 4: Linking census schedules to locations ===")
        if not dry_run:
            self.link_schedules_to_locations(schedules_file, places_lookup, stats)

        # Print summary
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
                    "county": row["county"],
                    "state": row["state"],
                    "county_ahcb": row["county_ahcb"],
                    "lat": float(row["lat"]) if row["lat"] else None,
                    "lon": float(row["lon"]) if row["lon"] else None,
                }
        return places

    def scan_transcribed_locations(self, schedules_file, stats):
        """
        Scan schedules CSV to find which locations were actually transcribed.
        Returns a dict mapping resource_id to location data.
        """
        transcribed = {}

        with open(schedules_file, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                resource_id = int(row["resource_id"])
                place_id = row.get("(d, e, f) Location", "").strip()
                unlisted_place = row.get("(d) Unlisted Populated Place", "").strip()

                # Track this schedule's location info
                transcribed[resource_id] = {
                    "place_id": None,
                    "unlisted_place": None,
                    "schedule_title": row["schedule_title"],
                }

                # Check for place_id (Apiary location)
                if place_id and place_id not in ["NULL", "MISSING", "ILLEGIBLE", ""]:
                    try:
                        place_id_int = int(place_id)
                        stats["place_ids_found"].add(place_id_int)
                        transcribed[resource_id]["place_id"] = place_id_int
                    except ValueError:
                        pass

                # Check for unlisted place name
                if unlisted_place and unlisted_place not in [
                    "NULL",
                    "MISSING",
                    "ILLEGIBLE",
                    "",
                ]:
                    stats["unlisted_places_found"].add(unlisted_place)
                    transcribed[resource_id]["unlisted_place"] = unlisted_place

        return transcribed

    def import_locations(self, places_lookup, stats, transcribed_data):
        """
        Import States, Counties, and PopulatedPlaces for transcribed locations only.
        """
        # Collect unique state/county combinations from transcribed data
        states_to_import = set()
        counties_to_import = defaultdict(set)  # state_code -> set of (county, ahcb)
        places_to_import = []

        # Gather what needs to be imported based on place_ids
        for place_id in stats["place_ids_found"]:
            if place_id in places_lookup:
                place_data = places_lookup[place_id]
                states_to_import.add(place_data["state"])
                counties_to_import[place_data["state"]].add(
                    (place_data["county"], place_data["county_ahcb"])
                )
                places_to_import.append((place_id, place_data))

        # Import States
        self.stdout.write(f"Importing {len(states_to_import)} states...")
        for state_code in states_to_import:
            state, created = State.objects.get_or_create(
                code=state_code, defaults={"name": self.get_state_name(state_code)}
            )
            if created:
                stats["states_created"] += 1
                self.stdout.write(f"  Created state: {state}")

        # Import Counties
        self.stdout.write(f"Importing counties for {len(states_to_import)} states...")
        for state_code, county_set in counties_to_import.items():
            state = State.objects.get(code=state_code)
            for county_name, ahcb_id in county_set:
                county, created = County.objects.get_or_create(
                    ahcb_id=ahcb_id, defaults={"name": county_name, "state": state}
                )
                if created:
                    stats["counties_created"] += 1
                    self.stdout.write(f"  Created county: {county}")

        # Import PopulatedPlaces (only those with place_ids)
        self.stdout.write(f"Importing {len(places_to_import)} populated places...")
        for place_id, place_data in places_to_import:
            county = County.objects.get(ahcb_id=place_data["county_ahcb"])
            place, created = PopulatedPlace.objects.get_or_create(
                place_id=place_id,
                defaults={
                    "name": place_data["name"],
                    "county": county,
                    "lat": place_data["lat"],
                    "lon": place_data["lon"],
                },
            )
            if created:
                stats["places_created"] += 1
                if stats["places_created"] % 100 == 0:
                    self.stdout.write(
                        f"  Imported {stats['places_created']} places..."
                    )

        self.stdout.write(
            self.style.SUCCESS(
                f"Imported {stats['states_created']} states, {stats['counties_created']} counties, {stats['places_created']} places"
            )
        )

    def link_schedules_to_locations(self, schedules_file, places_lookup, stats):
        """
        Link CensusSchedule records to County and PopulatedPlace based on transcribed data.
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
                        if place_id in places_lookup:
                            place_data = places_lookup[place_id]
                            county = County.objects.filter(
                                ahcb_id=place_data["county_ahcb"]
                            ).first()
                            populated_place = PopulatedPlace.objects.filter(
                                place_id=place_id
                            ).first()

                            if county:
                                schedule.county = county
                            if populated_place:
                                schedule.populated_place = populated_place

                            schedule.save(update_fields=["county", "populated_place"])
                            stats["schedules_linked_by_place_id"] += 1
                            continue
                    except (ValueError, KeyError):
                        pass

                # Try to link by unlisted place name
                if unlisted_place and unlisted_place not in [
                    "NULL",
                    "MISSING",
                    "ILLEGIBLE",
                    "",
                ]:
                    # For unlisted places, we don't have exact coordinates,
                    # but we can still link to county if we have it from Omeka API
                    # For now, just log these
                    stats["schedules_linked_by_unlisted_name"] += 1
                    self.stdout.write(
                        f"  Schedule {resource_id}: unlisted place '{unlisted_place}' (county linking via Omeka API recommended)"
                    )
                    continue

                # No location data transcribed
                stats["schedules_no_location"] += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Linked {stats['schedules_linked_by_place_id']} schedules by place_id"
            )
        )

    def get_state_name(self, state_code):
        """Return full state name from two-letter code"""
        state_names = {
            "AL": "Alabama",
            "AK": "Alaska",
            "AZ": "Arizona",
            "AR": "Arkansas",
            "CA": "California",
            "CO": "Colorado",
            "CT": "Connecticut",
            "DE": "Delaware",
            "FL": "Florida",
            "GA": "Georgia",
            "HI": "Hawaii",
            "ID": "Idaho",
            "IL": "Illinois",
            "IN": "Indiana",
            "IA": "Iowa",
            "KS": "Kansas",
            "KY": "Kentucky",
            "LA": "Louisiana",
            "ME": "Maine",
            "MD": "Maryland",
            "MA": "Massachusetts",
            "MI": "Michigan",
            "MN": "Minnesota",
            "MS": "Mississippi",
            "MO": "Missouri",
            "MT": "Montana",
            "NE": "Nebraska",
            "NV": "Nevada",
            "NH": "New Hampshire",
            "NJ": "New Jersey",
            "NM": "New Mexico",
            "NY": "New York",
            "NC": "North Carolina",
            "ND": "North Dakota",
            "OH": "Ohio",
            "OK": "Oklahoma",
            "OR": "Oregon",
            "PA": "Pennsylvania",
            "RI": "Rhode Island",
            "SC": "South Carolina",
            "SD": "South Dakota",
            "TN": "Tennessee",
            "TX": "Texas",
            "UT": "Utah",
            "VT": "Vermont",
            "VA": "Virginia",
            "WA": "Washington",
            "WV": "West Virginia",
            "WI": "Wisconsin",
            "WY": "Wyoming",
            "DC": "District of Columbia",
        }
        return state_names.get(state_code, state_code)

    def print_summary(self, stats, dry_run):
        """Print import summary"""
        self.stdout.write("\n" + "=" * 70)
        self.stdout.write(self.style.SUCCESS("IMPORT SUMMARY"))
        self.stdout.write("=" * 70)
        self.stdout.write(
            f"Transcribed place IDs found: {len(stats['place_ids_found'])}"
        )
        self.stdout.write(
            f"Unlisted places found: {len(stats['unlisted_places_found'])}"
        )
        self.stdout.write(f"States created: {stats['states_created']}")
        self.stdout.write(f"Counties created: {stats['counties_created']}")
        self.stdout.write(f"Populated places created: {stats['places_created']}")
        self.stdout.write(
            f"Schedules linked by place_id: {stats['schedules_linked_by_place_id']}"
        )
        self.stdout.write(
            f"Schedules with unlisted places: {stats['schedules_linked_by_unlisted_name']}"
        )
        self.stdout.write(
            f"Schedules with no location: {stats['schedules_no_location']}"
        )

        if dry_run:
            self.stdout.write(
                self.style.WARNING("\nDRY RUN - No changes were actually saved")
            )
