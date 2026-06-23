"""
Snapshot current transcribed data into the human_transcription JSONField.

Run this BEFORE any agentic transcription to preserve the human baseline.
Only populates records where human_transcription is currently null.
"""

from django.core.management.base import BaseCommand

from census.models import CensusSchedule


def serialize_schedule(schedule):
    """Serialize the human-transcribed data fields from a CensusSchedule and its relations."""
    data = {
        "schedule_fields": {
            "schedule_id": schedule.schedule_id,
            "schedule_title": schedule.schedule_title,
            "box": schedule.box,
            "notes": schedule.notes,
            "num_assistant_pastors": schedule.num_assistant_pastors,
            "respondent_name": schedule.respondent_name,
            "respondent_title": schedule.respondent_title,
            "respondent_po_address": schedule.respondent_po_address,
            "respondent_date_signed": schedule.respondent_date_signed,
            "date_received": str(schedule.date_received) if schedule.date_received else None,
            "district_stamp": schedule.district_stamp,
            "denomination_code_stamp": schedule.denomination_code_stamp,
            "marginalia": schedule.marginalia,
            "schedule_denomination_id": schedule.schedule_denomination_id,
        },
        "religious_bodies": [],
        "clergy": [],
    }

    for rb in schedule.church_details.all():
        rb_data = {
            "id": rb.id,
            "name": rb.name,
            "denomination_id": rb.denomination_id,
            "census_code": rb.census_code,
            "division": rb.division,
            "address": rb.address,
            "urban_rural_code": rb.urban_rural_code,
            "latitude": rb.latitude,
            "longitude": rb.longitude,
            "num_edifices": rb.num_edifices,
            "edifice_value": str(rb.edifice_value) if rb.edifice_value is not None else None,
            "edifice_debt": str(rb.edifice_debt) if rb.edifice_debt is not None else None,
            "has_pastors_residence": rb.has_pastors_residence,
            "residence_value": str(rb.residence_value) if rb.residence_value is not None else None,
            "residence_debt": str(rb.residence_debt) if rb.residence_debt is not None else None,
            "expenses": str(rb.expenses) if rb.expenses is not None else None,
            "benevolences": str(rb.benevolences) if rb.benevolences is not None else None,
            "total_expenditures": str(rb.total_expenditures) if rb.total_expenditures is not None else None,
            "membership": [],
        }

        for mem in rb.membership.all():
            rb_data["membership"].append({
                "id": mem.id,
                "male_members": mem.male_members,
                "female_members": mem.female_members,
                "total_members_by_sex": mem.total_members_by_sex,
                "members_under_13": mem.members_under_13,
                "members_13_and_older": mem.members_13_and_older,
                "total_members_by_age": mem.total_members_by_age,
                "sunday_school_num_officers_teachers": mem.sunday_school_num_officers_teachers,
                "sunday_school_num_scholars": mem.sunday_school_num_scholars,
                "vbs_num_officers_teachers": mem.vbs_num_officers_teachers,
                "vbs_num_scholars": mem.vbs_num_scholars,
                "weekday_num_officers_teachers": mem.weekday_num_officers_teachers,
                "weekday_num_scholars": mem.weekday_num_scholars,
                "parochial_num_administrators": mem.parochial_num_administrators,
                "parochial_num_elementary_teachers": mem.parochial_num_elementary_teachers,
                "parochial_num_secondary_teachers": mem.parochial_num_secondary_teachers,
                "parochial_num_elementary_scholars": mem.parochial_num_elementary_scholars,
                "parochial_num_secondary_scholars": mem.parochial_num_secondary_scholars,
            })

        data["religious_bodies"].append(rb_data)

    for clg in schedule.clergy.all():
        data["clergy"].append({
            "id": clg.id,
            "name": clg.name,
            "is_assistant": clg.is_assistant,
            "college": clg.college,
            "theological_seminary": clg.theological_seminary,
            "num_other_churches_served": clg.num_other_churches_served,
            "serving_congregation": clg.serving_congregation,
        })

    return data


class Command(BaseCommand):
    help = "Snapshot current transcribed data into human_transcription JSONField"

    def add_arguments(self, parser):
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help="Overwrite existing human_transcription data (default: skip populated records)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be updated without making changes",
        )

    def handle(self, *args, **options):
        queryset = CensusSchedule.objects.prefetch_related(
            "church_details__membership",
            "church_details__denomination",
            "clergy",
        ).select_related("schedule_denomination")

        if not options["overwrite"]:
            queryset = queryset.filter(human_transcription__isnull=True)

        total = queryset.count()
        if total == 0:
            self.stdout.write("No records to update.")
            return

        if options["dry_run"]:
            self.stdout.write(f"Dry run: would snapshot {total} records.")
            return

        updated = 0
        for schedule in queryset.iterator(chunk_size=500):
            schedule.human_transcription = serialize_schedule(schedule)
            schedule.save(update_fields=["human_transcription"])
            updated += 1
            if updated % 1000 == 0:
                self.stdout.write(f"  ...processed {updated}/{total}")

        self.stdout.write(self.style.SUCCESS(f"Snapshotted {updated} records."))
