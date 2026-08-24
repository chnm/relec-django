"""Read-only semantic comparison for immutable transcription outputs."""

import json
from collections import Counter
from decimal import Decimal, InvalidOperation

MISSING = object()

SCHEDULE_FIELDS = [
    ("populated_place_verbatim", "Populated place (verbatim)"),
    ("populated_place_id", "Matched populated place ID"),
    ("county_verbatim", "County (verbatim)"),
    ("state_verbatim", "State (verbatim)"),
    ("num_assistant_pastors", "Number of assistant pastors"),
]
RESPONDENT_FIELDS = [
    ("name", "Name"),
    ("title", "Title"),
    ("po_address", "P.O. address"),
    ("date_signed", "Date signed"),
]
PROCESSING_FIELDS = [
    ("date_received", "Date received"),
    ("district_stamp", "District stamp"),
    ("denomination_code_stamp", "Denomination code stamp"),
]
RELIGIOUS_BODY_FIELDS = [
    ("name", "Name"),
    ("census_code", "Census code"),
    ("division", "Division or conference"),
    ("address", "Address"),
    ("urban_rural_code", "Urban or rural"),
    ("num_edifices", "Number of edifices"),
    ("edifice_value", "Edifice value"),
    ("edifice_debt", "Edifice debt"),
    ("has_pastors_residence", "Has pastor's residence"),
    ("residence_value", "Residence value"),
    ("residence_debt", "Residence debt"),
    ("expenses", "Expenses"),
    ("benevolences", "Benevolences"),
    ("total_expenditures", "Total expenditures"),
]
MEMBERSHIP_FIELDS = [
    ("male_members", "Male members"),
    ("female_members", "Female members"),
    ("total_members_by_sex", "Total members by sex"),
    ("members_under_13", "Members under 13"),
    ("members_13_and_older", "Members 13 and older"),
    ("total_members_by_age", "Total members by age"),
    ("sunday_school_num_officers_teachers", "Sunday school officers/teachers"),
    ("sunday_school_num_scholars", "Sunday school scholars"),
    ("vbs_num_officers_teachers", "Vacation Bible school officers/teachers"),
    ("vbs_num_scholars", "Vacation Bible school scholars"),
    ("weekday_num_officers_teachers", "Weekday school officers/teachers"),
    ("weekday_num_scholars", "Weekday school scholars"),
    ("parochial_num_administrators", "Parochial school administrators"),
    ("parochial_num_elementary_teachers", "Elementary teachers"),
    ("parochial_num_secondary_teachers", "Secondary teachers"),
    ("parochial_num_elementary_scholars", "Elementary scholars"),
    ("parochial_num_secondary_scholars", "Secondary scholars"),
]
CLERGY_FIELDS = [
    ("name", "Name"),
    ("is_assistant", "Assistant"),
    ("college", "College"),
    ("theological_seminary", "Theological seminary"),
    ("num_other_churches_served", "Other churches served"),
    ("serving_congregation", "Serving this congregation"),
]


def normalize_transcription(data):
    """Map human snapshots and agent candidates into one display-only shape."""
    data = data or {}
    schedule = data.get("schedule_fields") or {}
    respondent = schedule.get("respondent")
    if not isinstance(respondent, dict):
        respondent = {
            "name": schedule.get("respondent_name", MISSING),
            "title": schedule.get("respondent_title", MISSING),
            "po_address": schedule.get("respondent_po_address", MISSING),
            "date_signed": schedule.get("respondent_date_signed", MISSING),
        }
    processing = schedule.get("processing")
    if not isinstance(processing, dict):
        processing = {
            "date_received": schedule.get("date_received", MISSING),
            "district_stamp": schedule.get("district_stamp", MISSING),
            "denomination_code_stamp": schedule.get(
                "denomination_code_stamp", MISSING
            ),
        }

    bodies = []
    for body in data.get("religious_bodies") or []:
        membership = body.get("membership", MISSING)
        if isinstance(membership, dict):
            memberships = [membership]
        elif isinstance(membership, list):
            memberships = membership
        else:
            memberships = []
        bodies.append({"fields": body, "memberships": memberships})

    return {
        "schedule": schedule,
        "respondent": respondent,
        "processing": processing,
        "religious_bodies": bodies,
        "clergy": data.get("clergy") or [],
        "marginalia": schedule.get("marginalia", MISSING),
        "ai_notes": schedule.get("ai_notes", MISSING),
    }


def build_comparison(left_data, right_data):
    """Return aligned sections without changing either source document."""
    left = normalize_transcription(left_data)
    right = normalize_transcription(right_data)
    sections = [
        _section("Schedule", SCHEDULE_FIELDS, left["schedule"], right["schedule"]),
        _section(
            "Respondent", RESPONDENT_FIELDS, left["respondent"], right["respondent"]
        ),
        _section(
            "Census Bureau processing",
            PROCESSING_FIELDS,
            left["processing"],
            right["processing"],
        ),
    ]

    body_count = max(
        len(left["religious_bodies"]), len(right["religious_bodies"])
    )
    for index in range(body_count):
        left_body = _item(left["religious_bodies"], index)
        right_body = _item(right["religious_bodies"], index)
        sections.append(
            _section(
                f"Religious body {index + 1}",
                RELIGIOUS_BODY_FIELDS,
                left_body.get("fields", {}),
                right_body.get("fields", {}),
                note="Bodies are aligned by their order on the schedule.",
            )
        )

        membership_count = max(
            len(left_body.get("memberships", [])),
            len(right_body.get("memberships", [])),
        )
        for membership_index in range(membership_count):
            sections.append(
                _section(
                    f"Religious body {index + 1}: membership "
                    f"{membership_index + 1}",
                    MEMBERSHIP_FIELDS,
                    _item(left_body.get("memberships", []), membership_index),
                    _item(right_body.get("memberships", []), membership_index),
                )
            )

    clergy_count = max(len(left["clergy"]), len(right["clergy"]))
    for index in range(clergy_count):
        sections.append(
            _section(
                f"Clergy {index + 1}",
                CLERGY_FIELDS,
                _item(left["clergy"], index),
                _item(right["clergy"], index),
                note="Clergy are aligned by their order on the schedule.",
            )
        )

    sections.extend(
        [
            _section(
                "Marginalia",
                [("value", "Transcribed marginalia")],
                {"value": left["marginalia"]},
                {"value": right["marginalia"]},
            ),
            _section(
                "Agent notes",
                [("value", "Notes")],
                {"value": left["ai_notes"]},
                {"value": right["ai_notes"]},
            ),
        ]
    )
    sections = [section for section in sections if section["rows"]]
    counts = Counter(
        row["status"] for section in sections for row in section["rows"]
    )
    return {
        "sections": sections,
        "counts": {
            "same": counts["same"],
            "equivalent": counts["equivalent"],
            "different": counts["different"],
            "one_missing": counts["one_missing"],
            "blank_zero": counts["blank_zero"],
        },
    }


def source_raw_json(source):
    return json.dumps(source.data, indent=2, sort_keys=True, default=str)


def comparison_row(
    label,
    left,
    right,
    *,
    decision_key="",
    selected="candidate",
    edited_base="",
    edited_value="",
    edit_type="text",
):
    """Build one display row with optional mixed-source decision metadata."""
    row = _row(label, left, right)
    edited_display = _display_value(edited_value)
    row.update(
        {
            "decision_key": decision_key,
            "selected": selected,
            "can_choose": bool(decision_key) and row["status"] != "same",
            "edited_base": edited_base,
            "edited_value": edited_value,
            "edited_display": edited_display["text"],
            "edited_input": edited_display["input"],
            "edit_type": edit_type,
        }
    )
    return row


def _section(title, fields, left, right, note=""):
    rows = []
    for key, label in fields:
        left_value = left.get(key, MISSING)
        right_value = right.get(key, MISSING)
        if left_value is MISSING and right_value is MISSING:
            continue
        rows.append(_row(label, left_value, right_value))
    return {"title": title, "note": note, "rows": rows}


def _row(label, left, right):
    status = _status(left, right)
    return {
        "label": label,
        "left": _display_value(left),
        "right": _display_value(right),
        "status": status,
        "status_label": {
            "same": "Same",
            "equivalent": "Equivalent format",
            "different": "Different",
            "one_missing": "One source only",
            "blank_zero": "Blank vs zero",
        }[status],
    }


def _status(left, right):
    if left is MISSING or right is MISSING:
        return "one_missing"
    if (_is_blank(left) and _is_zero(right)) or (
        _is_blank(right) and _is_zero(left)
    ):
        return "blank_zero"
    if _same(left, right):
        return "same"
    if _equivalent(left, right):
        return "equivalent"
    return "different"


def _same(left, right):
    if _is_blank(left) and _is_blank(right):
        return True
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    return type(left) is type(right) and left == right


def _equivalent(left, right):
    normalized_codes = {
        "r": "rural",
        "rural": "rural",
        "u": "urban",
        "urban": "urban",
    }
    if isinstance(left, str) and isinstance(right, str):
        left_code = normalized_codes.get(left.casefold())
        right_code = normalized_codes.get(right.casefold())
        if left_code is not None and left_code == right_code:
            return True
    try:
        return Decimal(str(left)) == Decimal(str(right))
    except (InvalidOperation, TypeError, ValueError):
        return False


def _display_value(value):
    if value is MISSING:
        return {"text": "Not captured", "kind": "missing", "input": ""}
    if _is_blank(value):
        return {"text": "Blank", "kind": "blank", "input": ""}
    if isinstance(value, bool):
        return {
            "text": "Yes" if value else "No",
            "kind": "value",
            "input": "true" if value else "false",
        }
    if isinstance(value, (dict, list)):
        return {
            "text": json.dumps(value, indent=2, sort_keys=True, default=str),
            "kind": "structured",
            "input": json.dumps(value, sort_keys=True, default=str),
        }
    return {"text": str(value), "kind": "value", "input": str(value)}


def _is_blank(value):
    return value is None or value == ""


def _is_zero(value):
    if isinstance(value, bool):
        return False
    try:
        return Decimal(str(value)) == 0
    except (InvalidOperation, TypeError, ValueError):
        return False


def _item(items, index):
    return items[index] if index < len(items) else {}
