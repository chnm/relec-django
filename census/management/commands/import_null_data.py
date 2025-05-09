import csv
import os
from datetime import datetime

from django.core.management.base import BaseCommand
from django.db import transaction

from census.models import (
    CensusSchedule,
    Clergy,
    Denomination,
    Membership,
    ReligiousBody,
)
from location.models import Location


class Command(BaseCommand):
    help = "Import census data from CSV file using NULL for missing/illegible values"

    def add_arguments(self, parser):
        parser.add_argument("csv_file", type=str, help="Path to the CSV file")
        parser.add_argument(
            "--limit", type=int, help="Limit the number of records to import", default=0
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete existing records before import",
            default=False,
        )

    def setup_error_log(self):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_dir = "logs"
        os.makedirs(log_dir, exist_ok=True)
        return open(f"{log_dir}/import_errors_{timestamp}.log", "w")

    def handle(self, *args, **options):
        self.error_log = self.setup_error_log()
        count = 0
        limit = options["limit"]
        reset = options["reset"]

        try:
            # Reset the database if requested
            if reset:
                self.stdout.write("Deleting existing records...")
                Clergy.objects.all().delete()
                Membership.objects.all().delete()
                ReligiousBody.objects.all().delete()
                CensusSchedule.objects.all().delete()
                self.stdout.write("Database reset complete.")

            with open(options["csv_file"], "r") as file:
                reader = csv.DictReader(file)

                total_rows = (
                    sum(1 for _ in open(options["csv_file"], "r")) - 1
                )  # Subtract header
                self.stdout.write(f"Found {total_rows} rows in the CSV file.")

                for row in reader:
                    try:
                        with transaction.atomic():
                            resource_id = row["resource_id"]
                            self.stdout.write(
                                f"\nProcessing row {resource_id} ({count + 1}/{total_rows})"
                            )

                            # Create CensusSchedule
                            census_schedule = self._create_census_schedule(row)

                            # Create Clergy if present
                            clergy_name = self._clean_value(
                                row.get("(25b) Name of Pastor")
                            )
                            if clergy_name:
                                self._create_clergy(
                                    row, census_schedule, is_assistant=False
                                )

                            # Create Assistant Clergy if present
                            assistant_pastors = self._clean_numeric(
                                row.get("(26) Number of Assistant Pastors")
                            )
                            if assistant_pastors and assistant_pastors > 0:
                                self._create_clergy(
                                    row, census_schedule, is_assistant=True
                                )

                            count += 1
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f"Successfully processed row {resource_id}"
                                )
                            )

                            if limit > 0 and count >= limit:
                                self.stdout.write(
                                    self.style.SUCCESS(
                                        f"Reached import limit of {limit} records."
                                    )
                                )
                                break

                    except Exception as e:
                        self.log_error(
                            f"Error processing row {row.get('resource_id', 'unknown')}: {str(e)}"
                        )
                        continue

            self.stdout.write(
                self.style.SUCCESS(f"Import completed. Processed {count} records.")
            )

        finally:
            self.error_log.close()

    def log_error(self, message):
        self.error_log.write(f"{datetime.now()}: {message}\n")
        self.stdout.write(self.style.WARNING(message))

    def _clean_value(self, value):
        """
        Clean a value from the CSV, handling NULL, MISSING, and ILLEGIBLE values
        Returns None for all of these cases
        """
        if (
            not value
            or value.strip() == ""
            or value.upper() == "NULL"
            or value == "MISSING"
            or value == "ILLEGIBLE"
        ):
            return None
        return value.strip()

    def _clean_numeric(self, value):
        """Convert string to numeric value, returning None for missing values"""
        clean_val = self._clean_value(value)
        if clean_val is None:
            return None
        try:
            if "." in clean_val:
                return float(clean_val)
            else:
                return int(clean_val)
        except (ValueError, TypeError):
            return None

    def _clean_boolean(self, value):
        """Convert Yes/No to boolean, returning None for missing values"""
        clean_val = self._clean_value(value)
        if clean_val is None:
            return None
        if isinstance(clean_val, str):
            if clean_val.lower() == "yes":
                return True
            elif clean_val.lower() == "no":
                return False
        return None

    def _create_census_schedule(self, row):
        # Get or create the schedule
        resource_id = int(row["resource_id"])
        census_schedule, created = CensusSchedule.objects.update_or_create(
            resource_id=resource_id,
            defaults={
                "schedule_title": row["schedule_title"],
                "schedule_id": row["schedule_id"],
                "datascribe_omeka_item_id": int(row["datascribe_omeka_item_id"]),
                "datascribe_item_id": int(row["datascribe_item_id"]),
                "datascribe_record_id": int(row["datascribe_record_id"]),
                "datascribe_original_image_path": row.get(
                    "datascribe_original_image_path", ""
                ),
                "omeka_storage_id": row.get("omeka_storage_id", ""),
            },
        )

        if created:
            self.stdout.write(f"Created new census schedule {resource_id}")
        else:
            self.stdout.write(f"Updated existing census schedule {resource_id}")

        return census_schedule

    def _create_religious_body(self, row, census_schedule):
        # Try to find existing religious body for this census schedule
        try:
            religious_body = ReligiousBody.objects.get(census_record=census_schedule)
            self.stdout.write(
                f"Religious body for census schedule {census_schedule.resource_id} already exists, updating..."
            )
        except ReligiousBody.DoesNotExist:
            religious_body = ReligiousBody(census_record=census_schedule)
            self.stdout.write(
                f"Creating new religious body for census schedule {census_schedule.resource_id}"
            )

        # Find denomination by denomination_id if available
        if row.get("denomination_id"):
            try:
                denomination = Denomination.objects.get(
                    denomination_id=row["denomination_id"]
                )
                religious_body.denomination = denomination
            except Denomination.DoesNotExist:
                self.stdout.write(
                    self.style.WARNING(
                        f"Denomination not found: {row['denomination_id']}"
                    )
                )

        # Find location by place_id if it exists
        location_id = self._clean_value(row.get("(d, e, f) Location"))
        if location_id:
            try:
                location = Location.objects.get(place_id=location_id)
                religious_body.location = location
            except Location.DoesNotExist:
                self.stdout.write(
                    self.style.WARNING(f"Location not found: {location_id}")
                )

        # Map data from row to model fields
        religious_body.name = self._clean_value(row.get("(c) Local Church Name"))
        religious_body.census_code = row.get("Census Code", "")
        religious_body.division = row.get("(b) Division", "")
        religious_body.address = self._clean_value(row.get("Address"))
        religious_body.urban_rural_code = self._clean_value(row.get("Urban/Rural Code"))

        # Handle numeric fields
        religious_body.num_edifices = self._clean_numeric(
            row.get("(7) Number of Church Edifices")
        )
        religious_body.edifice_value = self._clean_numeric(
            row.get("(8) Value of Church Edifices")
        )
        religious_body.edifice_debt = self._clean_numeric(
            row.get("(9) Debt on Church Edifices")
        )
        religious_body.has_pastors_residence = self._clean_boolean(
            row.get("(10) Ownership of Pastor's Residence")
        )
        religious_body.residence_value = self._clean_numeric(
            row.get("(11) Value of Pastor's Residence")
        )
        religious_body.residence_debt = self._clean_numeric(
            row.get("(12) Debt on Pastor's Residence")
        )

        # Financial fields
        religious_body.expenses = self._clean_numeric(row.get("(13) Expenses"))
        religious_body.benevolences = self._clean_numeric(row.get("(14) Benevolences"))
        religious_body.total_expenditures = self._clean_numeric(
            row.get("(15) Total Annual Expenditures")
        )

        religious_body.save()
        return religious_body

    def _create_membership(self, row, census_schedule, religious_body):
        # Try to find existing membership for this census schedule
        try:
            membership = Membership.objects.get(census_record=census_schedule)
            self.stdout.write(
                f"Membership for census schedule {census_schedule.resource_id} already exists, updating..."
            )
        except Membership.DoesNotExist:
            membership = Membership(
                census_record=census_schedule, religious_body=religious_body
            )
            self.stdout.write(
                f"Creating new membership for census schedule {census_schedule.resource_id}"
            )

        # Map data from row to model fields
        membership.male_members = self._clean_numeric(
            row.get("(1) Number of Members - Male")
        )
        membership.female_members = self._clean_numeric(
            row.get("(2) Number of Members - Female")
        )
        membership.total_members_by_sex = self._clean_numeric(
            row.get("(3) Total Number of Members by Sex")
        )
        membership.members_under_13 = self._clean_numeric(
            row.get("(4) Number of Members - Under 13")
        )
        membership.members_13_and_older = self._clean_numeric(
            row.get("(5) Number of Members - 13 and Older")
        )
        membership.total_members_by_age = self._clean_numeric(
            row.get("(6) Total Number of Members by Age")
        )

        # Sunday school data
        membership.sunday_school_num_officers_teachers = self._clean_numeric(
            row.get("(16) Sunday Schools - Number of Officers and Teachers")
        )
        membership.sunday_school_num_scholars = self._clean_numeric(
            row.get("(17) Sunday Schools - Number of Scholars")
        )

        # Vacation Bible School data
        membership.vbs_num_officers_teachers = self._clean_numeric(
            row.get("(18) Vacation Bible Schools - Number of Officers and Teachers")
        )
        membership.vbs_num_scholars = self._clean_numeric(
            row.get("(19) Vacation Bible Schools - Number of Scholars")
        )

        # Weekday Religious School data
        membership.weekday_num_officers_teachers = self._clean_numeric(
            row.get("(20) Week-day Religious Schools - Number of Officers and Teachers")
        )
        membership.weekday_num_scholars = self._clean_numeric(
            row.get("(21) Week-day Religious Schools - Number of Scholars")
        )

        # Parochial School data
        membership.parochial_num_administrators = self._clean_numeric(
            row.get("(22) Parochial Schools - Number of Administrators")
        )
        membership.parochial_num_elementary_teachers = self._clean_numeric(
            row.get("(23a) Parochial Schools - Number of Elementary Teachers")
        )
        membership.parochial_num_secondary_teachers = self._clean_numeric(
            row.get("(23b) Parochial Schools - Number of Secondary Teachers")
        )
        membership.parochial_num_elementary_scholars = self._clean_numeric(
            row.get("(24a) Parochial Schools - Number of Elementary Scholars")
        )
        membership.parochial_num_secondary_scholars = self._clean_numeric(
            row.get("(24b) Parochial Schools - Number of Secondary Scholars")
        )

        membership.save()
        return membership

    def _create_clergy(self, row, census_schedule, is_assistant=False):
        if is_assistant:
            name = self._clean_value(row.get("Name of Assistant Pastor"))
            college = self._clean_value(
                row.get("(30) Name of College - Assistant Pastor")
            )
            seminary = self._clean_value(
                row.get("(31) Name of Theological Seminary - Assistant Pastor")
            )
            num_churches = None
            serving_congregation = None
        else:
            name = self._clean_value(row.get("(25b) Name of Pastor"))
            college = self._clean_value(row.get("(28) Name of College - Pastor"))
            seminary = self._clean_value(
                row.get("(29) Name of Theological Seminary - Pastor")
            )
            num_churches = self._clean_numeric(
                row.get("(27) Number of Other Churches Served by Pastors")
            )
            serving_congregation = self._clean_boolean(
                row.get("(25a) Pastor Serving Congregation")
            )

        # Skip if no name
        if not name:
            return None

        # Look for existing clergy for this census schedule and assistant status
        try:
            # Filter by census schedule and assistant status
            existing_clergy = Clergy.objects.filter(
                census_schedule=census_schedule, is_assistant=is_assistant
            )

            if existing_clergy.exists():
                # Use the first match if there are multiple
                clergy = existing_clergy.first()
                self.stdout.write(
                    f"Clergy for census schedule {census_schedule.resource_id} already exists, updating..."
                )
            else:
                # Create new if none exists
                clergy = Clergy(
                    census_schedule=census_schedule,
                    name=name,
                    is_assistant=is_assistant,
                )
                self.stdout.write(
                    f"Creating new clergy for census schedule {census_schedule.resource_id}"
                )
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"Error retrieving clergy: {str(e)}"))
            # Create new if error occurs
            clergy = Clergy(
                census_schedule=census_schedule, name=name, is_assistant=is_assistant
            )

        # Update clergy details
        clergy.college = college
        clergy.theological_seminary = seminary
        clergy.num_other_churches_served = num_churches

        if not is_assistant:
            clergy.serving_congregation = serving_congregation

        clergy.save()
        return clergy
