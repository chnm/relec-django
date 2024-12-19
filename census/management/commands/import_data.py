import pandas as pd
from django.core.management.base import BaseCommand
from django.db import transaction
from census.models import ReligiousCensusRecord, Denomination
from church.models import Church, Membership
from education.models import SundaySchool, VacationBibleSchool, ParochialSchool
from clergy.models import Clergy
from location.models import State, County, City


class Command(BaseCommand):
    help = "Import census data from CSV file"

    def add_arguments(self, parser):
        parser.add_argument("csv_file", type=str, help="Path to the CSV file")

    def handle(self, *args, **options):
        try:
            # More robust CSV reading
            df = pd.read_csv(
                options["csv_file"],
                quoting=1,  # QUOTE_ALL
                escapechar="\\",
                on_bad_lines="warn",
            )

            self.stdout.write(
                self.style.SUCCESS(f"Successfully read CSV with {len(df)} rows")
            )

            # Drop any completely empty rows
            df = df.dropna(how="all")

            # Start the import process
            with transaction.atomic():
                for index, row in df.iterrows():
                    try:
                        # Create or get denomination
                        denomination, _ = Denomination.objects.get_or_create(
                            code=str(
                                row["denomination_id"]
                            )  # Convert to string in case it's numeric
                        )

                        # Create the main census record
                        census_record = ReligiousCensusRecord.objects.create(
                            resource_id=row["resource_id"],
                            denomination=denomination,
                            schedule_title=row["schedule_title"],
                            schedule_id=row["schedule_id"],
                            datascribe_omeka_item_id=row["datascribe_omeka_item_id"],
                            datascribe_item_id=row["datascribe_item_id"],
                            datascribe_record_id=row["datascribe_record_id"],
                        )

                        # Handle location
                        # Extract state from location field or use a default
                        location_parts = (
                            str(row["(d, e, f) Location"]).split(",")
                            if pd.notna(row["(d, e, f) Location"])
                            else ["Unknown"]
                        )
                        state_name = (
                            location_parts[-1].strip() if location_parts else "Unknown"
                        )

                        state, _ = State.objects.get_or_create(name=state_name)

                        # Create Church record
                        church = Church.objects.create(
                            census_record=census_record,
                            name=(
                                row["(c) Local Church Name"]
                                if pd.notna(row["(c) Local Church Name"])
                                else "Unknown"
                            ),
                            state=state,
                            urban_rural_code=(
                                row["Urban/Rural Code"]
                                if pd.notna(row["Urban/Rural Code"])
                                else ""
                            ),
                            address=row["Address"] if pd.notna(row["Address"]) else "",
                        )

                        # Create Membership record linked to both Church and CensusRecord
                        Membership.objects.create(
                            census_record=census_record,  # Link to census record
                            church=church,  # Link to church
                            male_members=(
                                row["(1) Number of Members - Male"]
                                if pd.notna(row["(1) Number of Members - Male"])
                                else 0
                            ),
                            female_members=(
                                row["(2) Number of Members - Female"]
                                if pd.notna(row["(2) Number of Members - Female"])
                                else 0
                            ),
                            members_under_13=(
                                row["(4) Number of Members - Under 13"]
                                if pd.notna(row["(4) Number of Members - Under 13"])
                                else 0
                            ),
                            members_13_and_older=(
                                row["(5) Number of Members - 13 and Older"]
                                if pd.notna(row["(5) Number of Members - 13 and Older"])
                                else 0
                            ),
                        )

                        # Create Sunday School record if data exists
                        if pd.notna(
                            row["(16) Sunday Schools - Number of Officers and Teachers"]
                        ):
                            SundaySchool.objects.create(
                                census_record=census_record,
                                church=church,  # Add this line
                                num_officers_teachers=row[
                                    "(16) Sunday Schools - Number of Officers and Teachers"
                                ],
                                num_scholars=(
                                    row["(17) Sunday Schools - Number of Scholars"]
                                    if pd.notna(
                                        row["(17) Sunday Schools - Number of Scholars"]
                                    )
                                    else 0
                                ),
                            )

                        # Create VBS record if data exists
                        if pd.notna(
                            row[
                                "(18) Vacation Bible Schools - Number of Officers and Teachers"
                            ]
                        ):
                            VacationBibleSchool.objects.create(
                                census_record=census_record,
                                church=church,  # Add this line
                                num_officers_teachers=row[
                                    "(18) Vacation Bible Schools - Number of Officers and Teachers"
                                ],
                                num_scholars=(
                                    row[
                                        "(19) Vacation Bible Schools - Number of Scholars"
                                    ]
                                    if pd.notna(
                                        row[
                                            "(19) Vacation Bible Schools - Number of Scholars"
                                        ]
                                    )
                                    else 0
                                ),
                            )

                        # Create Parochial School record if data exists
                        if pd.notna(
                            row["(22) Parochial Schools - Number of Administrators"]
                        ):
                            try:
                                # Attempt to convert values to numbers, if 'yes' appears, treat as missing data
                                num_elem_teachers = row[
                                    "(23a) Parochial Schools - Number of Elementary Teachers"
                                ]
                                if (
                                    isinstance(num_elem_teachers, str)
                                    and num_elem_teachers.lower() == "yes"
                                ):
                                    num_elem_teachers = None

                                ParochialSchool.objects.create(
                                    census_record=census_record,
                                    church=church,
                                    num_administrators=row[
                                        "(22) Parochial Schools - Number of Administrators"
                                    ],
                                    num_elementary_teachers=(
                                        num_elem_teachers
                                        if pd.notna(num_elem_teachers)
                                        else 0
                                    ),
                                    num_secondary_teachers=(
                                        row[
                                            "(23b) Parochial Schools - Number of Secondary Teachers"
                                        ]
                                        if pd.notna(
                                            row[
                                                "(23b) Parochial Schools - Number of Secondary Teachers"
                                            ]
                                        )
                                        else 0
                                    ),
                                    num_elementary_scholars=(
                                        row[
                                            "(24a) Parochial Schools - Number of Elementary Scholars"
                                        ]
                                        if pd.notna(
                                            row[
                                                "(24a) Parochial Schools - Number of Elementary Scholars"
                                            ]
                                        )
                                        else 0
                                    ),
                                    num_secondary_scholars=(
                                        row[
                                            "(24b) Parochial Schools - Number of Secondary Scholars"
                                        ]
                                        if pd.notna(
                                            row[
                                                "(24b) Parochial Schools - Number of Secondary Scholars"
                                            ]
                                        )
                                        else 0
                                    ),
                                )

                            except (ValueError, TypeError) as e:
                                self.stdout.write(
                                    self.style.WARNING(
                                        f'Skipping parochial school creation for record {row["resource_id"]} due to data conversion issue: {str(e)}'
                                    )
                                )

                        # Create Pastor record if name exists
                        if pd.notna(row["(25b) Name of Pastor"]):
                            Clergy.objects.create(
                                census_record=census_record,
                                church=church,  # Add this line
                                name=row["(25b) Name of Pastor"],
                                is_assistant=False,
                                college=(
                                    row["(28) Name of College - Pastor"]
                                    if pd.notna(row["(28) Name of College - Pastor"])
                                    else None
                                ),
                                theological_seminary=(
                                    row["(29) Name of Theological Seminary - Pastor"]
                                    if pd.notna(
                                        row[
                                            "(29) Name of Theological Seminary - Pastor"
                                        ]
                                    )
                                    else None
                                ),
                                num_other_churches_served=(
                                    row[
                                        "(27) Number of Other Churches Served by Pastors"
                                    ]
                                    if pd.notna(
                                        row[
                                            "(27) Number of Other Churches Served by Pastors"
                                        ]
                                    )
                                    else 0
                                ),
                            )

                        if index % 100 == 0:  # Print progress every 100 records
                            self.stdout.write(
                                self.style.SUCCESS(f"Imported {index + 1} records...")
                            )

                    except Exception as e:
                        self.stdout.write(
                            self.style.ERROR(
                                f"Error importing record at row {index + 1}: {str(e)}"
                            )
                        )
                        raise

            self.stdout.write(
                self.style.SUCCESS(f"Successfully imported {len(df)} records")
            )

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error during import: {str(e)}"))
