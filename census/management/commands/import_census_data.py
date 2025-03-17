import csv
from decimal import Decimal

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
    help = "Import census data from CSV file"

    def add_arguments(self, parser):
        parser.add_argument("csv_file", type=str, help="Path to the CSV file")

    def handle(self, *args, **options):
        with open(options["csv_file"], "r") as file:
            reader = csv.DictReader(file)

            for row in reader:
                try:
                    with transaction.atomic():
                        self.stdout.write(f"\nProcessing row {row['resource_id']}")

                        # Create CensusSchedule
                        census_schedule = self._create_census_schedule(row)

                        # Create Clergy
                        if self._clean_value(row.get("(25b) Name of Pastor")):
                            self._create_clergy(
                                row, census_schedule, is_assistant=False
                            )

                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(
                            f"Error processing row {row['resource_id']}: {str(e)}"
                        )
                    )
                    continue

                self.stdout.write(
                    self.style.SUCCESS(
                        f"Successfully processed row {row['resource_id']}"
                    )
                )

    def _clean_value(self, value):
        """Clean a value from the CSV, handling NULL values"""
        if not value or value.strip() == "" or value.upper() == "NULL":
            return None
        return value.strip()

    def _create_census_schedule(self, row):
        return CensusSchedule.objects.create(
            resource_id=int(row["resource_id"]),
            schedule_title=row["schedule_title"],
            schedule_id=row["schedule_id"],
            datascribe_omeka_item_id=int(row["datascribe_omeka_item_id"]),
            datascribe_item_id=int(row["datascribe_item_id"]),
            datascribe_record_id=int(row["datascribe_record_id"]),
        )

    def _create_religious_body(self, row, census_schedule):
        # Find denomination by denomination_id
        denomination = Denomination.objects.get(denomination_id=row["denomination_id"])

        # Find location by place_id if it exists
        location = None
        if self._clean_value(row["(d, e, f) Location"]):
            location = Location.objects.get(place_id=int(row["(d, e, f) Location"]))

        name = self._clean_value(row["(c) Local Church Name"])

        return ReligiousBody.objects.create(
            census_record=census_schedule,
            denomination=denomination,
            name=name,
            census_code=row["Census Code"],
            division=row["(b) Division"],
            address=self._clean_value(row["Address"]),
            location=location,
            urban_rural_code=self._clean_value(row["Urban/Rural Code"]),
            num_edifices=int(
                self._clean_value(row["(7) Number of Church Edifices"]) or 0
            ),
            edifice_value=Decimal(
                self._clean_value(row["(8) Value of Church Edifices"]) or 0
            ),
            edifice_debt=Decimal(
                self._clean_value(row["(9) Debt on Church Edifices"]) or 0
            ),
            has_pastors_residence=(
                self._clean_value(row["(10) Ownership of Pastor's Residence"]).lower()
                == "yes"
                if self._clean_value(row["(10) Ownership of Pastor's Residence"])
                else False
            ),
            residence_value=(
                Decimal(self._clean_value(row["(11) Value of Pastor's Residence"]) or 0)
                if self._clean_value(row["(11) Value of Pastor's Residence"])
                else None
            ),
            residence_debt=(
                Decimal(self._clean_value(row["(12) Debt on Pastor's Residence"]) or 0)
                if self._clean_value(row["(12) Debt on Pastor's Residence"])
                else None
            ),
            expenses=Decimal(self._clean_value(row["(13) Expenses"]) or 0),
            benevolences=Decimal(self._clean_value(row["(14) Benevolences"]) or 0),
            total_expenditures=Decimal(
                self._clean_value(row["(15) Total Annual Expenditures"]) or 0
            ),
        )

    def _create_membership(self, row, census_schedule, religious_body):
        return Membership.objects.create(
            census_record=census_schedule,
            church=religious_body,
            male_members=int(
                self._clean_value(row["(1) Number of Members - Male"]) or 0
            ),
            female_members=int(
                self._clean_value(row["(2) Number of Members - Female"]) or 0
            ),
            members_under_13=int(
                self._clean_value(row["(4) Number of Members - Under 13"]) or 0
            ),
            members_13_and_older=int(
                self._clean_value(row["(5) Number of Members - 13 and Older"]) or 0
            ),
            sunday_school_num_officers_teachers=int(
                self._clean_value(
                    row["(16) Sunday Schools - Number of Officers and Teachers"]
                )
                or 0
            ),
            sunday_school_num_scholars=int(
                self._clean_value(row["(17) Sunday Schools - Number of Scholars"]) or 0
            ),
            vbs_num_officers_teachers=int(
                self._clean_value(
                    row["(18) Vacation Bible Schools - Number of Officers and Teachers"]
                )
                or 0
            ),
            vbs_num_scholars=int(
                self._clean_value(
                    row["(19) Vacation Bible Schools - Number of Scholars"]
                )
                or 0
            ),
            parochial_num_administrators=int(
                self._clean_value(
                    row["(22) Parochial Schools - Number of Administrators"]
                )
                or 0
            ),
            parochial_num_elementary_teachers=int(
                self._clean_value(
                    row["(23a) Parochial Schools - Number of Elementary Teachers"]
                )
                or 0
            ),
            parochial_num_secondary_teachers=int(
                self._clean_value(
                    row["(23b) Parochial Schools - Number of Secondary Teachers"]
                )
                or 0
            ),
            parochial_num_elementary_scholars=int(
                self._clean_value(
                    row["(24a) Parochial Schools - Number of Elementary Scholars"]
                )
                or 0
            ),
            parochial_num_secondary_scholars=int(
                self._clean_value(
                    row["(24b) Parochial Schools - Number of Secondary Scholars"]
                )
                or 0
            ),
        )

    def _create_clergy(self, row, census_schedule, is_assistant=False):
        if is_assistant:
            name = self._clean_value(row.get("Assistant Pastor Name"))
            college = self._clean_value(row["(30) Name of College - Assistant Pastor"])
            seminary = self._clean_value(
                row["(31) Name of Theological Seminary - Assistant Pastor"]
            )
        else:
            name = self._clean_value(row["(25b) Name of Pastor"])
            college = self._clean_value(row["(28) Name of College - Pastor"])
            seminary = self._clean_value(
                row["(29) Name of Theological Seminary - Pastor"]
            )

        if not name:
            return None

        return Clergy.objects.create(
            census_schedule=census_schedule,
            name=name,
            is_assistant=is_assistant,
            college=college,
            theological_seminary=seminary,
            num_other_churches_served=(
                int(
                    self._clean_value(
                        row["(27) Number of Other Churches Served by Pastors"]
                    )
                    or 0
                )
                if not is_assistant
                else 0
            ),
        )
