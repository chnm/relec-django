"""
Export full congregation-level data (one row per ReligiousBody) to CSV:
identity, county and denomination identifiers, location, membership, and
finances — for records at any transcription stage.

Membership and finance columns are only populated for transcribed records; for
un-digitized records they are blank, while the county/denomination identifiers
and schedule linkage are still present.

Runs directly against the ORM — no pagination, no HTTP timeouts.

Background: created 2026-07-07 for an external researcher who requested a
transfer of the full congregation-level data with county and denomination
identifiers, including records not yet fully digitized. The public
`/religious-bodies/` API is not a reliable bulk path (the urban_rural filter and
deep pagination time out with 502s), so this command is the supported way to
regenerate that export. Re-run any time; it reflects the current DB state.

Examples:
    uv run python manage.py export_congregations_csv -o congregations.csv
    uv run python manage.py export_congregations_csv --count        # counts only
    uv run python manage.py export_congregations_csv --status approved -o approved.csv
"""

import csv
import sys

from django.core.management.base import BaseCommand

from census.models import ReligiousBody

# Membership fields, copied verbatim from the first Membership row of each
# congregation (matches how the public API surfaces membership).
MEMBERSHIP_FIELDS = [
    "male_members",
    "female_members",
    "total_members_by_sex",
    "members_under_13",
    "members_13_and_older",
    "total_members_by_age",
    "sunday_school_num_officers_teachers",
    "sunday_school_num_scholars",
    "vbs_num_officers_teachers",
    "vbs_num_scholars",
    "weekday_num_officers_teachers",
    "weekday_num_scholars",
    "parochial_num_administrators",
    "parochial_num_elementary_teachers",
    "parochial_num_secondary_teachers",
    "parochial_num_elementary_scholars",
    "parochial_num_secondary_scholars",
]

# Finance fields live directly on ReligiousBody.
FINANCE_FIELDS = [
    "num_edifices",
    "edifice_value",
    "edifice_debt",
    "has_pastors_residence",
    "residence_value",
    "residence_debt",
    "expenses",
    "benevolences",
    "total_expenditures",
]

COLUMNS = (
    [
        # Identity / keys
        "religious_body_id",
        "schedule_id",
        "name",
        "transcription_status",
        "census_code",
        "division",
        # County
        "county_ahcb",
        "county_name",
        "state_name",
        # Denomination
        "denomination_id",
        "denomination_name",
        "family_census",
        "family_relec",
        # Location
        "has_location",
        "city_name",
        "lat",
        "lon",
        "address",
        "urban_rural_code",
    ]
    + MEMBERSHIP_FIELDS
    + FINANCE_FIELDS
)


def base_queryset():
    return (
        ReligiousBody.objects.select_related(
            "denomination",
            "census_record",
            "census_record__county",
            "census_record__county__state",
            "census_record__populated_place",
        )
        .prefetch_related("membership")
        .order_by("census_record__schedule_id", "pk")
    )


def row_for(rb):
    cs = rb.census_record
    county = cs.county if cs else None
    pp = cs.populated_place if cs else None
    denom = rb.denomination
    # membership is prefetched; take the first row (matches the API).
    membership = next(iter(rb.membership.all()), None)

    row = {
        "religious_body_id": rb.id,
        "schedule_id": cs.schedule_id if cs else None,
        "name": rb.name or None,
        "transcription_status": cs.transcription_status if cs else None,
        "census_code": rb.census_code or None,
        "division": rb.division or None,
        "county_ahcb": county.ahcb_id if county else None,
        "county_name": county.name if county else None,
        "state_name": county.state.code if county and county.state else None,
        "denomination_id": denom.denomination_id if denom else None,
        "denomination_name": denom.name if denom else None,
        "family_census": denom.family_census if denom else None,
        "family_relec": denom.family_relec if denom else None,
        "has_location": pp is not None,
        "city_name": pp.name if pp else None,
        "lat": pp.lat if pp else None,
        "lon": pp.lon if pp else None,
        "address": rb.address or None,
        "urban_rural_code": rb.urban_rural_code or None,
    }
    for f in MEMBERSHIP_FIELDS:
        row[f] = getattr(membership, f) if membership else None
    for f in FINANCE_FIELDS:
        row[f] = getattr(rb, f)
    return row


class Command(BaseCommand):
    help = "Export full congregation-level data (county, denomination, membership, finances) to CSV."

    def add_arguments(self, parser):
        parser.add_argument(
            "-o", "--output", default=None,
            help="Output CSV path (default: stdout).",
        )
        parser.add_argument(
            "--status", default=None,
            help="Filter by transcription_status (e.g. approved). Default: all records.",
        )
        parser.add_argument(
            "--count", action="store_true",
            help="Report counts only; write no CSV. Use to verify sync against the server.",
        )

    def handle(self, *args, **options):
        if options["count"]:
            self._report_counts()
            return

        qs = base_queryset()
        if options["status"]:
            qs = qs.filter(census_record__transcription_status=options["status"])

        fh = open(options["output"], "w", newline="") if options["output"] else sys.stdout

        written = with_membership = 0
        try:
            writer = csv.DictWriter(fh, fieldnames=COLUMNS)
            writer.writeheader()
            for rb in qs.iterator(chunk_size=2000):
                row = row_for(rb)
                writer.writerow(row)
                written += 1
                if row["total_members_by_sex"] is not None:
                    with_membership += 1
        finally:
            if fh is not sys.stdout:
                fh.close()

        target = options["output"] or "stdout"
        self.stderr.write(self.style.SUCCESS(f"Wrote {written} rows -> {target}"))
        self.stderr.write(
            f"  rows with membership data: {with_membership} "
            f"({self._pct(with_membership, written)})"
        )

    def _report_counts(self):
        from django.db.models import Count

        total = ReligiousBody.objects.count()
        self.stdout.write(f"Total ReligiousBody rows: {total}")
        self.stdout.write("By transcription_status:")
        rows = (
            ReligiousBody.objects.values("census_record__transcription_status")
            .annotate(n=Count("id"))
            .order_by("-n")
        )
        for r in rows:
            self.stdout.write(
                f"  {r['census_record__transcription_status'] or '(none)':<14} {r['n']}"
            )

    @staticmethod
    def _pct(n, total):
        return f"{100 * n / total:.2f}%" if total else "0%"
