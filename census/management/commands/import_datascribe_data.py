import csv
import os
from datetime import datetime
from decimal import Decimal, InvalidOperation

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

# Constants for special values in the data
MISSING = "MISSING"
ILLEGIBLE = "ILLEGIBLE"
NULL = "NULL"


def clean_value(value, convert_to_numeric=False):
    """
    Clean a value from the input data

    Args:
        value (str): The value to clean
        convert_to_numeric (bool, optional): Whether to attempt numeric conversion. Defaults to False.

    Returns:
        int, Decimal, str, or None: The cleaned value or None if it's a special value
    """
    if value in [MISSING, ILLEGIBLE, NULL, "", None]:
        return None

    # If we don't need numeric conversion, just return the string
    if not convert_to_numeric:
        return value

    # If requested, try to convert to numeric
    # First try integer
    try:
        if str(value).isdigit() or (
            str(value).startswith("-") and str(value)[1:].isdigit()
        ):
            return int(value)
    except (ValueError, TypeError):
        pass

    # Then try decimal
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        # If all conversion attempts fail, return string value
        return value


def clean_numeric_value(value):
    """
    Convert string value to appropriate numeric type or None

    Args:
        value (str): The value to convert

    Returns:
        int, Decimal, or None: The converted value or None if it's a special value
    """
    return clean_value(value, convert_to_numeric=True)


def map_workflow_status(reviewed, is_approved):
    """
    Map CSV workflow columns to Django transcription_status field

    Args:
        reviewed (str): "1", "0", or None
        is_approved (str): "1", "0", or None

    Returns:
        str: Django status value
    """
    # Clean the values first
    reviewed_clean = clean_value(reviewed)
    approved_clean = clean_value(is_approved)

    if approved_clean == "1":
        return "approved"
    elif reviewed_clean == "1" and approved_clean == "0":
        return "completed"  # reviewed but not approved
    elif reviewed_clean == "1" and approved_clean is None:
        return "needs_review"  # reviewed, approval status unknown
    elif reviewed_clean == "0":
        return "in_progress"  # explicitly marked as not reviewed
    else:  # reviewed is None or empty
        return "unassigned"  # no workflow status set


class Command(BaseCommand):
    help = "Import DataScribe census data from CSV file"

    def add_arguments(self, parser):
        parser.add_argument("--csv_file", type=str, help="Path to the CSV file")
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
        return open(f"{log_dir}/datascribe_import_errors_{timestamp}.log", "w")

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

                            # Create ReligiousBody
                            religious_body = self._create_religious_body(
                                row, census_schedule
                            )

                            # Create Membership
                            self._create_membership(
                                row, census_schedule, religious_body
                            )

                            # Create Clergy if present
                            if (
                                row.get("(25b) Name of Pastor")
                                and row.get("(25b) Name of Pastor") != ""
                                and row.get("(25b) Name of Pastor") != NULL
                            ):
                                self._create_clergy(
                                    row,
                                    census_schedule,
                                )

                            # Create Assistant Clergy if present
                            assistant_pastors = row.get(
                                "(26) Number of Assistant Pastors", "0"
                            )
                            if (
                                assistant_pastors != "0"
                                and assistant_pastors != MISSING
                                and assistant_pastors != NULL
                                and assistant_pastors != ""
                                and row.get("Name of Assistant Pastor")
                                and row.get("Name of Assistant Pastor")
                                not in ["", NULL]
                            ):
                                self._create_clergy(
                                    row,
                                    census_schedule,
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

    def _create_census_schedule(self, row):
        # Get or create the schedule
        resource_id = clean_numeric_value(row["resource_id"])
        if resource_id is None:
            raise ValueError(f"Invalid resource_id: {row['resource_id']}")

        # Clean numeric values for other ID fields, skip if NULL
        omeka_item_id = clean_numeric_value(row["datascribe_omeka_item_id"])
        item_id = clean_numeric_value(row["datascribe_item_id"])
        record_id = clean_numeric_value(row["datascribe_record_id"])

        # Map workflow status from CSV columns
        workflow_status = map_workflow_status(
            row.get("reviewed"), row.get("is_approved")
        )

        census_schedule, created = CensusSchedule.objects.update_or_create(
            resource_id=resource_id,
            defaults={
                "schedule_title": row["schedule_title"],
                "schedule_id": row["schedule_id"],
                "transcription_status": workflow_status,
                "datascribe_omeka_item_id": omeka_item_id,
                "datascribe_item_id": item_id,
                "datascribe_record_id": record_id,
                "datascribe_original_image_path": clean_value(
                    row.get("datascribe_original_image_path", "")
                ),
                "omeka_storage_id": clean_value(row.get("omeka_storage_id", "")),
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
        if row.get("(d, e, f) Location") and row.get("(d, e, f) Location") not in [
            MISSING,
            ILLEGIBLE,
            "",
            NULL,
            None,
        ]:
            try:
                location = Location.objects.get(place_id=row["(d, e, f) Location"])
                religious_body.location = location
            except Location.DoesNotExist:
                self.stdout.write(
                    self.style.WARNING(
                        f"Location not found: {row.get('(d, e, f) Location')}"
                    )
                )

        # Map data from row to model fields, using clean_value for strings
        religious_body.name = clean_value(row.get("(c) Local Church Name", ""))
        religious_body.census_code = clean_value(row.get("Census Code", ""))
        religious_body.division = clean_value(row.get("(b) Division", ""))
        religious_body.address = clean_value(row.get("Address", ""))
        religious_body.urban_rural_code = clean_value(row.get("Urban/Rural Code", ""))

        # Handle numeric fields with clean_numeric_value
        religious_body.num_edifices = clean_numeric_value(
            row.get("(7) Number of Church Edifices", "")
        )
        religious_body.edifice_value = clean_numeric_value(
            row.get("(8) Value of Church Edifices", "")
        )
        religious_body.edifice_debt = clean_numeric_value(
            row.get("(9) Debt on Church Edifices", "")
        )

        # Handle has_pastors_residence field (convert "Yes"/"No"/"Missing"/"Illegible"/blank to True/False/None)
        pastors_residence = row.get("(10) Ownership of Pastor's Residence", "")
        if pastors_residence == "Yes":
            religious_body.has_pastors_residence = True
        elif pastors_residence == "No":
            religious_body.has_pastors_residence = False
        else:
            # For "Missing", "Illegible", blank or any other value
            religious_body.has_pastors_residence = None

        religious_body.residence_value = clean_numeric_value(
            row.get("(11) Value of Pastor's Residence", "")
        )
        religious_body.residence_debt = clean_numeric_value(
            row.get("(12) Debt on Pastor's Residence", "")
        )

        # Financial fields
        religious_body.expenses = clean_numeric_value(row.get("(13) Expenses", ""))
        religious_body.benevolences = clean_numeric_value(
            row.get("(14) Benevolences", "")
        )
        religious_body.total_expenditures = clean_numeric_value(
            row.get("(15) Total Annual Expenditures", "")
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

        # Map data from row to model fields using clean_numeric_value
        membership.male_members = clean_numeric_value(
            row.get("(1) Number of Members - Male", "")
        )
        membership.female_members = clean_numeric_value(
            row.get("(2) Number of Members - Female", "")
        )
        membership.total_members_by_sex = clean_numeric_value(
            row.get("(3) Total Number of Members by Sex", "")
        )
        membership.members_under_13 = clean_numeric_value(
            row.get("(4) Number of Members - Under 13", "")
        )
        membership.members_13_and_older = clean_numeric_value(
            row.get("(5) Number of Members - 13 and Older", "")
        )
        membership.total_members_by_age = clean_numeric_value(
            row.get("(6) Total Number of Members by Age", "")
        )

        # Sunday school data
        membership.sunday_school_num_officers_teachers = clean_numeric_value(
            row.get("(16) Sunday Schools - Number of Officers and Teachers", "")
        )
        membership.sunday_school_num_scholars = clean_numeric_value(
            row.get("(17) Sunday Schools - Number of Scholars", "")
        )

        # Vacation Bible School data
        membership.vbs_num_officers_teachers = clean_numeric_value(
            row.get("(18) Vacation Bible Schools - Number of Officers and Teachers", "")
        )
        membership.vbs_num_scholars = clean_numeric_value(
            row.get("(19) Vacation Bible Schools - Number of Scholars", "")
        )

        # Weekday Religious School data
        membership.weekday_num_officers_teachers = clean_numeric_value(
            row.get(
                "(20) Week-day Religious Schools - Number of Officers and Teachers", ""
            )
        )
        membership.weekday_num_scholars = clean_numeric_value(
            row.get("(21) Week-day Religious Schools - Number of Scholars", "")
        )

        # Parochial School data
        membership.parochial_num_administrators = clean_numeric_value(
            row.get("(22) Parochial Schools - Number of Administrators", "")
        )
        membership.parochial_num_elementary_teachers = clean_numeric_value(
            row.get("(23a) Parochial Schools - Number of Elementary Teachers", "")
        )
        membership.parochial_num_secondary_teachers = clean_numeric_value(
            row.get("(23b) Parochial Schools - Number of Secondary Teachers", "")
        )
        membership.parochial_num_elementary_scholars = clean_numeric_value(
            row.get("(24a) Parochial Schools - Number of Elementary Scholars", "")
        )
        membership.parochial_num_secondary_scholars = clean_numeric_value(
            row.get("(24b) Parochial Schools - Number of Secondary Scholars", "")
        )

        membership.save()
        return membership

    def _create_clergy(self, row, census_schedule):
        # Determine if this is for primary pastor or assistant
        is_assistant = False
        if "(26) Number of Assistant Pastors" in row and row.get(
            "(26) Number of Assistant Pastors"
        ) not in ["0", "", MISSING, NULL]:
            is_assistant = True

        # Get the appropriate field values based on whether this is a pastor or assistant
        if is_assistant:
            raw_name = row.get("Name of Assistant Pastor", "")
            serving_congregation = None  # Assistants don't have this field
            college = clean_value(
                row.get("(30) Name of College - Assistant Pastor", "")
            )
            seminary = clean_value(
                row.get("(31) Name of Theological Seminary - Assistant Pastor", "")
            )
        else:
            raw_name = row.get("(25b) Name of Pastor", "")
            serving_congregation = row.get("(25a) Pastor Serving Congregation", "")
            college = clean_value(row.get("(28) Name of College - Pastor", ""))
            seminary = clean_value(
                row.get("(29) Name of Theological Seminary - Pastor", "")
            )

        # Get cleaned name (for name we want to preserve ILLEGIBLE to indicate that there was a pastor)
        name = raw_name
        if raw_name in [MISSING, NULL, "", None]:
            name = None

        # Convert serving_congregation to Boolean if it's "Yes" or "No"
        if serving_congregation == "Yes":
            serving_congregation = True
        elif serving_congregation == "No":
            serving_congregation = False
        else:
            serving_congregation = None

        # Get the number of other churches served using our helper
        num_churches = clean_numeric_value(
            row.get("(27) Number of Other Churches Served by Pastors", "")
        )

        # Skip empty names (if name is None, we should skip)
        if name is None:
            self.stdout.write(
                f"Skipping clergy creation for schedule {census_schedule.resource_id} - no name provided"
            )
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
                    name=name,  # Name is already cleaned
                    is_assistant=is_assistant,
                )
                self.stdout.write(
                    f"Creating new clergy for census schedule {census_schedule.resource_id}"
                )
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"Error retrieving clergy: {str(e)}"))
            # Create new if error occurs
            clergy = Clergy(
                census_schedule=census_schedule,
                name=name,  # Name is already cleaned
                is_assistant=is_assistant,
            )

        # Update clergy details
        clergy.name = name  # Name should already be properly cleaned
        clergy.college = college
        clergy.theological_seminary = seminary
        clergy.num_other_churches_served = num_churches
        clergy.serving_congregation = serving_congregation

        clergy.save()
        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully created/updated clergy {clergy.name} for schedule {census_schedule.resource_id}"
            )
        )
        return clergy
