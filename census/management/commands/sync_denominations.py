import datetime
import os

import requests
from django.core.management import BaseCommand
from requests.exceptions import RequestException

from census.models import Denomination


class Command(BaseCommand):
    help = "Synchronize denominations from the API"

    def setup_error_log(self):
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        log_dir = "logs"
        os.makedirs(log_dir, exist_ok=True)
        return open(f"{log_dir}/sync_denominations_errors_{timestamp}.log", "w")

    def log_error(self, message):
        self.error_log.write(f"{datetime.datetime.now()}: {message}\n")
        self.stdout.write(self.style.WARNING(message))

    def handle(self, *args, **options):
        self.error_log = self.setup_error_log()
        skipped_count = 0
        success_count = 0

        try:
            response = requests.get(
                "https://data.chnm.org/relcensus/denominations", timeout=30
            )
            response.raise_for_status()
            denominations_data = response.json()

            for denom_data in denominations_data:
                # Check if any string field exceeds maximum length
                too_long = False
                for field, value in denom_data.items():
                    if isinstance(value, str):
                        max_length = 50 if field == "denomination_id" else 255
                        if len(value) > max_length:
                            self.log_error(
                                f"Skipping denomination with id={denom_data.get('denomination_id', 'unknown')}: {field} value exceeds {max_length} characters ({len(value)} chars)"
                            )
                            too_long = True
                            break

                if too_long:
                    skipped_count += 1
                    continue

                try:
                    # Map the API response fields to our model fields
                    # Adjust as needed based on the actual API response structure
                    Denomination.objects.update_or_create(
                        denomination_id=denom_data["denomination_id"],
                        defaults={
                            "name": denom_data["name"],
                            "short_name": denom_data["short_name"],
                            "family_relec": denom_data.get("family_relec", ""),
                            "family_census": denom_data.get("family_census", ""),
                        },
                    )
                    success_count += 1
                except Exception as e:
                    self.log_error(
                        f"Error saving denomination with id={denom_data.get('denomination_id', 'unknown')}: {str(e)}"
                    )
                    skipped_count += 1

            self.stdout.write(
                self.style.SUCCESS(
                    f"Synchronized {success_count} denominations, skipped {skipped_count} denominations with values exceeding maximum length"
                )
            )
        except RequestException as e:
            self.stdout.write(self.style.ERROR(f"Connection error: {str(e)}"))
            self.stdout.write(
                self.style.WARNING(
                    "Make sure the API is accessible at https://data.chnm.org/relcensus/denominations"
                )
            )
        finally:
            self.error_log.close()
