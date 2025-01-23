import csv
import os
from datetime import datetime

from django.core.management.base import BaseCommand
from django.db import transaction

from census.models import Denomination
from location.models import City, County, Location, State

STATE_MAPPING = {
    # Full names to abbreviations
    "Alabama": "AL",
    "Alaska": "AK",
    "Arizona": "AZ",
    "Arkansas": "AR",
    "California": "CA",
    "Colorado": "CO",
    "Connecticut": "CT",
    "Delaware": "DE",
    "Florida": "FL",
    "Georgia": "GA",
    "Hawaii": "HI",
    "Idaho": "ID",
    "Illinois": "IL",
    "Indiana": "IN",
    "Iowa": "IA",
    "Kansas": "KS",
    "Kentucky": "KY",
    "Louisiana": "LA",
    "Maine": "ME",
    "Maryland": "MD",
    "Massachusetts": "MA",
    "Michigan": "MI",
    "Minnesota": "MN",
    "Mississippi": "MS",
    "Missouri": "MO",
    "Montana": "MT",
    "Nebraska": "NE",
    "Nevada": "NV",
    "New Hampshire": "NH",
    "New Jersey": "NJ",
    "New Mexico": "NM",
    "New York": "NY",
    "North Carolina": "NC",
    "North Dakota": "ND",
    "Ohio": "OH",
    "Oklahoma": "OK",
    "Oregon": "OR",
    "Pennsylvania": "PA",
    "Rhode Island": "RI",
    "South Carolina": "SC",
    "South Dakota": "SD",
    "Tennessee": "TN",
    "Texas": "TX",
    "Utah": "UT",
    "Vermont": "VT",
    "Virginia": "VA",
    "Washington": "WA",
    "Washington DC": "DC",
    "West Virginia": "WV",
    "Wisconsin": "WI",
    "Wyoming": "WY",
}


class Command(BaseCommand):
    help = "Import denomination and locations data from CSV files"

    def add_arguments(self, parser):
        parser.add_argument(
            "--denominations", type=str, help="Path to denominations CSV"
        )
        parser.add_argument("--locations", type=str, help="Path to locations CSV")

    def setup_error_log(self):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_dir = "import_logs"
        os.makedirs(log_dir, exist_ok=True)
        return open(f"{log_dir}/import_errors_{timestamp}.log", "w")

    def handle(self, *args, **options):
        self.error_log = self.setup_error_log()
        try:
            if options["denominations"]:
                self.import_denominations(options["denominations"])
            if options["locations"]:
                self.import_locations(options["locations"])
        finally:
            self.error_log.close()

    def log_error(self, message):
        self.error_log.write(f"{datetime.now()}: {message}\n")
        self.stdout.write(self.style.WARNING(message))

    def get_or_create_state(self, state_input):
        try:
            # Create reverse mapping for abbreviations
            abbrev_to_name = {v: k for k, v in STATE_MAPPING.items()}

            # Check if input is abbreviation
            if state_input in abbrev_to_name:
                state_name = abbrev_to_name[state_input]
                abbreviation = state_input
            else:
                state_name = state_input
                abbreviation = STATE_MAPPING[state_name]
            state, created = State.objects.get_or_create(
                name=state_name, defaults={"abbreviation": abbreviation}
            )
            return state
        except KeyError:
            self.log_error(f"Unknown state: {state_name}")
            return None

    def get_or_create_county(self, county_name, state):
        if not state:
            return None
        county, created = County.objects.get_or_create(name=county_name, state=state)
        return county

    def get_or_create_city(self, city_name, state, county):
        if not state:
            return None
        city, created = City.objects.get_or_create(
            name=city_name, state=state, defaults={"county": county}
        )
        return city

    @transaction.atomic
    def import_denominations(self, filepath):
        self.stdout.write("Importing denominations...")
        with open(filepath, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    Denomination.objects.update_or_create(
                        denomination_id=row["denomination_id"],
                        defaults={
                            "name": row["name"],
                            "family_census": row["family_census"],
                            "family_arda": row["family_arda"],
                        },
                    )
                except Exception as e:
                    self.log_error(
                        f"Error importing denomination {row.get('denomination_id')}: {str(e)}"
                    )
                    continue

    @transaction.atomic
    def import_locations(self, filepath):
        self.stdout.write("Importing locations...")
        with open(filepath, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    state = self.get_or_create_state(row["state"])
                    if not state:
                        continue

                    county = self.get_or_create_county(row["county"], state)
                    city = self.get_or_create_city(row["place"], state, county)

                    Location.objects.update_or_create(
                        place_id=row["place_id"],
                        defaults={
                            "state": state,
                            "county": county,
                            "city": city,
                            "map_name": row["map_name"],
                            "county_ahcb": row["county_ahcb"],
                            "lat": float(row["lat"]),
                            "lon": float(row["lon"]),
                        },
                    )
                except Exception as e:
                    self.log_error(
                        f"Error importing location {row.get('place_id')}: {str(e)}"
                    )
                    continue
