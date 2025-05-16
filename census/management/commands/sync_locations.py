import datetime
import os

import requests
from django.core.management import BaseCommand
from requests.exceptions import RequestException

from location.models import Location


class Command(BaseCommand):
    help = "Synronize locations from the Postgres API"

    def setup_error_log(self):
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        log_dir = "logs"
        os.makedirs(log_dir, exist_ok=True)
        return open(f"{log_dir}/sync_locations_errors_{timestamp}.log", "w")

    def log_error(self, message):
        self.error_log.write(f"{datetime.datetime.now()}: {message}\n")
        self.stdout.write(self.style.WARNING(message))

    def handle(self, *args, **options):
        self.error_log = self.setup_error_log()
        skipped_count = 0
        success_count = 0

        try:
            response = requests.get(
                "http://localhost:8090/relcensus/cities", timeout=30
            )
            response.raise_for_status()
            locations_data = response.json()

            for loc_data in locations_data:
                # Check if any string field exceeds 250 characters
                too_long = False
                for field, value in loc_data.items():
                    if isinstance(value, str) and len(value) > 250:
                        self.log_error(
                            f"Skipping location with place_id={loc_data.get('place_id', 'unknown')}: {field} value exceeds 250 characters ({len(value)} chars)"
                        )
                        too_long = True
                        break

                if too_long:
                    skipped_count += 1
                    continue

                try:
                    Location.objects.update_or_create(
                        place_id=loc_data["place_id"],
                        city=loc_data["city"],
                        county=loc_data["county"],
                        state=loc_data["state"],
                        map_name=loc_data["map_name"],
                        county_ahcb=loc_data["county_ahcb"],
                        defaults={
                            "lon": loc_data["lon"],
                            "lat": loc_data["lat"],
                        },
                    )
                    success_count += 1
                except Exception as e:
                    self.log_error(
                        f"Error saving location with place_id={loc_data.get('place_id', 'unknown')}: {str(e)}"
                    )
                    skipped_count += 1

            self.stdout.write(
                self.style.SUCCESS(
                    f"Synchronized {success_count} locations, skipped {skipped_count} locations with values exceeding 250 characters"
                )
            )
        except RequestException as e:
            self.stdout.write(self.style.ERROR(f"Connection error: {str(e)}"))
            self.stdout.write(
                self.style.WARNING(
                    "Make sure the API server is running at http://localhost:8090"
                )
            )
        finally:
            self.error_log.close()
