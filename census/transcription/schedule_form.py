"""Regroup reconciliation review sections into the printed 1926 form layout.

Decision keys and rows are untouched; this only decides where each row is
drawn so the reviewer sees the same blocks and question numbers as the image.
"""

from copy import deepcopy

# (kind, field) -> (block, printed question number). Order here is form order.
_PLACEMENT = {}
for _block, _kind, _fields in (
    ("schedule", "schedule", (("populated_place_id", ""),)),
    (
        "header",
        "body",
        (
            ("division", "b"),
            ("name", "c"),
            ("address", "d"),
            ("census_code", ""),
            ("urban_rural_code", ""),
        ),
    ),
    (
        "membership",
        "membership",
        (
            ("male_members", "1"),
            ("female_members", "2"),
            ("total_members_by_sex", "3"),
            ("members_under_13", "4"),
            ("members_13_and_older", "5"),
            ("total_members_by_age", "6"),
        ),
    ),
    (
        "schools",
        "membership",
        (
            ("sunday_school_num_officers_teachers", "16"),
            ("sunday_school_num_scholars", "17"),
            ("vbs_num_officers_teachers", "18"),
            ("vbs_num_scholars", "19"),
            ("weekday_num_officers_teachers", "20"),
            ("weekday_num_scholars", "21"),
            ("parochial_num_administrators", "22"),
            ("parochial_num_elementary_teachers", "23a"),
            ("parochial_num_secondary_teachers", "23b"),
            ("parochial_num_elementary_scholars", "24a"),
            ("parochial_num_secondary_scholars", "24b"),
        ),
    ),
    (
        "buildings",
        "body",
        (
            ("num_edifices", "7"),
            ("edifice_value", "8"),
            ("edifice_debt", "9"),
            ("has_pastors_residence", "10"),
            ("residence_value", "11"),
            ("residence_debt", "12"),
        ),
    ),
    (
        "expenditures",
        "body",
        (
            ("expenses", "13"),
            ("benevolences", "14"),
            ("total_expenditures", "15"),
        ),
    ),
    ("pastor", "schedule", (("num_assistant_pastors", "26"),)),
    (
        "pastor",
        "clergy",
        (
            ("name", "25"),
            ("is_assistant", ""),
            ("num_other_churches_served", "27"),
            ("college", "28"),
            ("theological_seminary", "29"),
            ("serving_congregation", ""),
        ),
    ),
    (
        "footer",
        "schedule",
        (
            ("respondent_name", ""),
            ("respondent_title", ""),
            ("respondent_date_signed", ""),
            ("respondent_po_address", ""),
        ),
    ),
    (
        "stamps",
        "schedule",
        (
            ("date_received", ""),
            ("district_stamp", ""),
            ("denomination_code_stamp", ""),
        ),
    ),
):
    for _order, (_field, _number) in enumerate(_fields):
        _PLACEMENT[(_kind, _field)] = (_block, _number, _order)

BODY_BLOCKS = ("header", "membership", "schools", "buildings", "expenditures")


def schedule_form_layout(sections):
    form = {
        "schedule": [],
        "bodies": [],
        "pastor": [],
        "footer": [],
        "stamps": [],
        "other": [],
        "context": [],
    }
    body = None
    for section in sections:
        if section["decision_scope"] == "automatic":
            form["context"].append(section)
            continue
        kind = section["kind"]
        if kind == "body":
            body = {"title": section["title"], **{b: [] for b in BODY_BLOCKS}}
            form["bodies"].append(body)
        elif kind == "membership" and body is None:
            body = {"title": "", **{b: [] for b in BODY_BLOCKS}}
            form["bodies"].append(body)
        for block, panel in _split(section):
            target = body[block] if block in BODY_BLOCKS else form[block]
            target.append(panel)
    return form


def _split(section):
    """Split one section into (block, panel) pairs in form order."""
    buckets = {}
    for row in section["rows"]:
        block, number, order = _PLACEMENT.get(
            (section["kind"], row["field"]), ("other", "", 0)
        )
        row = {**row, "number": number}
        buckets.setdefault(block, []).append((order, row))
    panels = []
    for block, rows in buckets.items():
        panel = {
            key: deepcopy(value)
            for key, value in section.items()
            if key != "rows"
        }
        # The retain/remove radio for an unmatched entity renders once.
        if panels:
            panel.pop("entity_decision", None)
        panel["rows"] = [row for _, row in sorted(rows, key=lambda r: r[0])]
        panels.append((block, panel))
    return panels
