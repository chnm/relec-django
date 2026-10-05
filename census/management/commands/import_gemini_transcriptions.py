"""Import a collaborator's Gemini transcriptions as an immutable agent run.

Reads one denomination directory from the collaborator package
(``records/*.json``, ``generation.json``, ``export/api-candidates.jsonl``).
Records are keyed by the API's religious-body id, which differs between
databases, so we match on the schedule ``resource_id`` in ``urls.self``. Gemini's bounding
boxes and validation output ride along under ``_``-prefixed keys, which
reconciliation ignores.
"""

import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from census.models import CensusSchedule, ScheduleTranscription, TranscriptionRun
from census.transcription.contracts import (
    CONTRACT_VERSION,
    CandidateValidationError,
    load_contract,
    validate_candidate,
)

PLACE_MATCHED = {"exact", "existing"}
RESOURCE_URL = re.compile(r"/record/(\d+)/")


def _resource_id(record):
    match = RESOURCE_URL.search(record["api_metadata"]["urls"]["self"])
    return int(match.group(1))


def _text(value):
    """Gemini uses "NA" for confirmed blank and "" for unreadable; both are null here."""
    if value is None:
        return None
    value = str(value).strip()
    return None if value.upper() in ("", "NA") else value


def _int(value, path, notes):
    text = _text(value)
    if text is None:
        return None
    try:
        number = int(Decimal(re.sub(r"[$,\s]", "", text)))
    except InvalidOperation:
        notes.append(f"{path}: unparseable value {text!r} dropped.")
        return None
    if number < 0:
        notes.append(f"{path}: negative value {text!r} dropped.")
        return None
    return number


def _bool(value):
    return {"TRUE": True, "FALSE": False}.get(str(value).strip().upper())


def _school(value):
    """Our contract treats No/None college or seminary answers as null."""
    text = _text(value)
    return None if text and text.upper() == "NO" else text


def gemini_candidate(result, place_id=None):
    """Map one Gemini extraction result onto the relec-1926-v1 candidate contract."""
    notes = []
    ident = result["identification"]
    loc = result["location"]
    prop = result["edifice_property"]
    mem = result["membership"]
    exp = result["expenditures"]
    pastor = result["pastor"]

    def num(section, key, data):
        return _int(data.get(key), f"{section}.{key}", notes)

    membership = {
        name: num(section, key, result[section])
        for name, section, key in [
            ("male_members", "membership", "q1_male_members"),
            ("female_members", "membership", "q2_female_members"),
            ("total_members_by_sex", "membership", "q3_total_members"),
            ("members_under_13", "membership", "q4_members_under_13"),
            ("members_13_and_older", "membership", "q5_members_13_and_over"),
            ("total_members_by_age", "membership", "q6_total_members_by_age"),
            ("sunday_school_num_officers_teachers", "sunday_school", "q16_officers_teachers"),
            ("sunday_school_num_scholars", "sunday_school", "q17_scholars"),
            ("vbs_num_officers_teachers", "vacation_bible_school", "q18_officers_teachers"),
            ("vbs_num_scholars", "vacation_bible_school", "q19_scholars"),
            ("weekday_num_officers_teachers", "weekday_religious_school", "q20_officers_teachers"),
            ("weekday_num_scholars", "weekday_religious_school", "q21_scholars"),
            ("parochial_num_administrators", "parochial_school", "q22_administrators"),
            ("parochial_num_elementary_teachers", "parochial_school", "q23a_elementary_teachers"),
            ("parochial_num_secondary_teachers", "parochial_school", "q23b_secondary_teachers"),
            ("parochial_num_elementary_scholars", "parochial_school", "q24a_elementary_scholars"),
            ("parochial_num_secondary_scholars", "parochial_school", "q24b_secondary_scholars"),
        ]
    }

    urban_rural = _text(loc.get("urban_rural"))
    body = {
        "name": _text(ident.get("qc_church_name")),
        "census_code": _text(ident.get("denomination_code")),
        "division": _text(ident.get("qb_division")),
        "address": _text(loc.get("street_address")),
        "urban_rural_code": urban_rural if urban_rural in ("U", "R") else None,
        "membership": membership,
        "num_edifices": num("edifice_property", "q7_number_of_edifices", prop),
        "edifice_value": num("edifice_property", "q8_value_of_edifice_usd", prop),
        "edifice_debt": num("edifice_property", "q9_debt_on_edifice_usd", prop),
        "has_pastors_residence": _bool(prop.get("q10_owns_parsonage")),
        "residence_value": num("edifice_property", "q11_value_of_parsonage_usd", prop),
        "residence_debt": num("edifice_property", "q12_debt_on_parsonage_usd", prop),
        "expenses": num("expenditures", "q13_current_expenses_usd", exp),
        "benevolences": num("expenditures", "q14_benevolences_missions_usd", exp),
        "total_expenditures": num("expenditures", "q15_total_expenditures_usd", exp),
    }

    clergy = []
    principal = {
        "name": _text(pastor.get("q25_name")),
        "is_assistant": False,
        "college": _school(pastor.get("q28_college")),
        "theological_seminary": _school(pastor.get("q29_theological_seminary")),
        "num_other_churches_served": num("pastor", "q27_num_other_churches_served", pastor),
        "serving_congregation": None,
    }
    if any(principal[k] is not None for k in ("name", "college", "theological_seminary")):
        clergy.append(principal)
    for assistant in result.get("assistant_pastors") or []:
        entry = {
            "name": _text(assistant.get("name")),
            "is_assistant": True,
            "college": _school(assistant.get("q30_college")),
            "theological_seminary": _school(assistant.get("q31_theological_seminary")),
            "num_other_churches_served": None,
            "serving_congregation": None,
        }
        if any(entry[k] is not None for k in ("name", "college", "theological_seminary")):
            clergy.append(entry)

    confidence = result.get("confidence") or {}
    if confidence.get("notes"):
        notes.insert(0, confidence["notes"])
    if confidence.get("fields_flagged_low_confidence"):
        notes.append(
            "Flagged: " + ", ".join(confidence["fields_flagged_low_confidence"])
        )

    marginalia = _text(result.get("bureau_marginalia"))
    cert = result.get("certification") or {}
    return {
        "schema_version": CONTRACT_VERSION,
        "schedule_fields": {
            "populated_place_verbatim": _text(loc.get("qd_city_town_village")),
            "populated_place_id": place_id,
            "county_verbatim": _text(loc.get("qe_county")),
            "state_verbatim": _text(loc.get("qf_state")),
            "num_assistant_pastors": num("pastor", "q26_num_assistant_pastors", pastor),
            "respondent": {
                "name": _text(cert.get("filled_by_name")),
                "title": _text(cert.get("filled_by_position")),
                "po_address": _text(cert.get("filled_by_address")),
                "date_signed": _text(cert.get("date_filled")),
            },
            "processing": {
                "date_received": _text(ident.get("date_received_stamp")),
                "district_stamp": None,
                "denomination_code_stamp": None,
            },
            "marginalia": [
                {"page_location": "unspecified", "marginalia_transcription": marginalia}
            ]
            if marginalia
            else [],
            "ai_notes": "\n".join(notes) or None,
        },
        "religious_bodies": [body],
        "clergy": clergy,
    }


def _matched_places(denomination_dir):
    path = denomination_dir / "export" / "api-candidates.jsonl"
    if not path.is_file():
        return {}
    matches = {}
    for line in path.read_text().splitlines():
        row = json.loads(line)
        resolution = row.get("place_resolution") or {}
        if resolution.get("status") in PLACE_MATCHED and resolution.get("place_id"):
            matches[row["record_id"]] = resolution["place_id"]
    return matches


class Command(BaseCommand):
    help = "Import one denomination of Gemini transcriptions as an agent run"

    def add_arguments(self, parser):
        parser.add_argument(
            "denomination_dir",
            help="Package directory such as gemini/denominations/0-9-6_latter-day-saints",
        )
        parser.add_argument("--run-key", help="Override the derived run key")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        root = Path(options["denomination_dir"])
        records_dir = root / "records"
        if not records_dir.is_dir():
            raise CommandError(f"No records/ directory in {root}")
        generation = json.loads((root / "generation.json").read_text())
        code = root.name.split("_", 1)[0]
        run_key = options["run_key"] or (
            f"{generation['model']}-{generation['transcription_policy']}-{code}"
        ).replace(".", "-")

        run = TranscriptionRun.objects.filter(key=run_key).first()
        if run and run.kind != "agent":
            raise CommandError(f"Run {run_key!r} exists with kind {run.kind!r}.")

        schema = load_contract()["schema"]
        places = _matched_places(root)
        records = [
            json.loads(p.read_text())
            for p in sorted(records_dir.glob("*.json"), key=lambda p: int(p.stem))
        ]
        schedules = CensusSchedule.objects.select_related("county").in_bulk(
            [_resource_id(r) for r in records], field_name="resource_id"
        )
        done = (
            set(run.schedule_transcriptions.values_list("census_schedule_id", flat=True))
            if run
            else set()
        )

        pending, skipped = [], []
        for record in records:
            record_id = record["record_id"]
            schedule = schedules.get(_resource_id(record))
            extraction = record.get("extraction")
            if schedule is None:
                skipped.append(f"{record_id}: no schedule with resource_id {_resource_id(record)}")
                continue
            if schedule.pk in done:
                continue
            if schedule.schedule_id != record["api_metadata"]["schedule_id"]:
                skipped.append(
                    f"{record_id}: schedule_id {schedule.schedule_id!r} != "
                    f"{record['api_metadata']['schedule_id']!r}"
                )
                continue
            if not extraction:
                skipped.append(f"{record_id}: no extraction")
                continue

            place_id = places.get(record_id)
            if place_id and not (
                schedule.county_id
                and schedule.county.places.filter(place_id=place_id).exists()
            ):
                place_id = None
            candidate = gemini_candidate(extraction["result"], place_id)
            try:
                validate_candidate(candidate, schedule, schema=schema)
            except CandidateValidationError as exc:
                skipped.append(f"{record_id}: {exc}")
                continue

            candidate["_field_locations"] = extraction.get("field_locations") or {}
            candidate["_gemini_validation"] = record.get("validation")
            candidate["_provenance"] = {
                key: extraction.get(key)
                for key in ("model", "revision", "extracted_at", "batch_job_id", "source_sha1")
            } | {"religious_body_id": record_id}
            pending.append((schedule, candidate))

        for line in skipped:
            self.stderr.write(f"  skipped {line}")

        if options["dry_run"]:
            self.stdout.write(
                f"Dry run: would import {len(pending)} into {run_key!r} "
                f"({len(done)} already imported, {len(skipped)} skipped)."
            )
            return

        if run is None:
            run = TranscriptionRun.objects.create(
                key=run_key,
                kind="agent",
                metadata={
                    **generation,
                    "source": "collaborator Gemini package",
                    "denomination_code": code,
                    "contract_version": CONTRACT_VERSION,
                },
            )
        for schedule, candidate in pending:
            ScheduleTranscription.objects.create(
                census_schedule=schedule, run=run, data=candidate
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Imported {len(pending)} into {run.key!r} "
                f"({len(done)} already imported, {len(skipped)} skipped)."
            )
        )
