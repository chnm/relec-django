"""Preview and atomically apply schedule-level reconciliation decisions."""

import hashlib
import json
from collections import Counter
from copy import deepcopy
from datetime import date
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction

from census.models import (
    CensusSchedule,
    Clergy,
    Membership,
    ReconciliationSource,
    ReligiousBody,
    ScheduleReconciliation,
    ScheduleTranscription,
)
from census.transcription.comparison import CLERGY_FIELDS as DISPLAY_CLERGY_FIELDS
from census.transcription.comparison import (
    MEMBERSHIP_FIELDS as DISPLAY_MEMBERSHIP_FIELDS,
)
from census.transcription.comparison import (
    MISSING,
)
from census.transcription.comparison import (
    PROCESSING_FIELDS as DISPLAY_PROCESSING_FIELDS,
)
from census.transcription.comparison import RELIGIOUS_BODY_FIELDS as DISPLAY_BODY_FIELDS
from census.transcription.comparison import (
    comparison_row,
)
from census.transcription.contracts import (
    CONTRACT_VERSION,
    CandidateValidationError,
    validate_candidate,
)
from location.models import PopulatedPlace

DECISION_VERSION = "schedule-reconciliation-v3"
SCHEDULE_FIELDS = (
    "num_assistant_pastors",
    "respondent_name",
    "respondent_title",
    "respondent_po_address",
    "respondent_date_signed",
    "date_received",
    "district_stamp",
    "denomination_code_stamp",
    "marginalia",
    "ai_notes",
)
BODY_FIELDS = (
    "name",
    "census_code",
    "division",
    "address",
    "urban_rural_code",
    "num_edifices",
    "edifice_value",
    "edifice_debt",
    "has_pastors_residence",
    "residence_value",
    "residence_debt",
    "expenses",
    "benevolences",
    "total_expenditures",
)
MEMBERSHIP_FIELDS = (
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
)
CLERGY_FIELDS = (
    "name",
    "is_assistant",
    "college",
    "theological_seminary",
    "num_other_churches_served",
    "serving_congregation",
)
NONNEGATIVE_FIELDS = {
    "num_assistant_pastors",
    "num_edifices",
    "edifice_value",
    "edifice_debt",
    "residence_value",
    "residence_debt",
    "expenses",
    "benevolences",
    "total_expenditures",
    "num_other_churches_served",
    *MEMBERSHIP_FIELDS,
}
DECIMAL_FIELDS = {
    "edifice_value",
    "edifice_debt",
    "residence_value",
    "residence_debt",
    "expenses",
    "benevolences",
    "total_expenditures",
}
BOOLEAN_FIELDS = {
    "has_pastors_residence",
    "is_assistant",
    "serving_congregation",
}
INTEGER_FIELDS = (NONNEGATIVE_FIELDS - DECIMAL_FIELDS) | {"populated_place_id"}
DATE_FIELDS = {"date_received"}
SCHEDULE_FIELD_GROUPS = (
    (
        "Schedule",
        (
            ("populated_place_id", "Matched populated place ID"),
            ("num_assistant_pastors", "Number of assistant pastors"),
        ),
    ),
    (
        "Respondent",
        (
            ("respondent_name", "Name"),
            ("respondent_title", "Title"),
            ("respondent_po_address", "P.O. address"),
            ("respondent_date_signed", "Date signed"),
        ),
    ),
    (
        "Census Bureau processing",
        tuple(DISPLAY_PROCESSING_FIELDS),
    ),
)
AI_CONTEXT_FIELD_GROUPS = (
    ("Marginalia", (("marginalia", "Transcribed marginalia"),)),
    ("Agent notes", (("ai_notes", "Notes"),)),
)
BODY_LABELS = dict(DISPLAY_BODY_FIELDS)
MEMBERSHIP_LABELS = dict(DISPLAY_MEMBERSHIP_FIELDS)
CLERGY_LABELS = dict(DISPLAY_CLERGY_FIELDS)


class ReconciliationError(ValueError):
    """Base error safe to show on the reviewer screen."""


class ReconciliationValidationError(ReconciliationError):
    pass


class StaleReconciliationError(ReconciliationError):
    pass


def schedule_graph_queryset():
    return CensusSchedule.objects.select_related(
        "county__state",
        "populated_place__county__state",
        "schedule_denomination",
    ).prefetch_related(
        "church_details__membership",
        "church_details__denomination",
        "clergy",
    )


def serialize_canonical(schedule):
    """Serialize only the canonical graph governed by reconciliation."""
    schedule_fields = {
        "populated_place_id": (
            schedule.populated_place.place_id if schedule.populated_place else None
        ),
        "num_assistant_pastors": schedule.num_assistant_pastors,
        "respondent_name": schedule.respondent_name,
        "respondent_title": schedule.respondent_title,
        "respondent_po_address": schedule.respondent_po_address,
        "respondent_date_signed": schedule.respondent_date_signed,
        "date_received": (
            schedule.date_received.isoformat() if schedule.date_received else None
        ),
        "district_stamp": schedule.district_stamp,
        "denomination_code_stamp": schedule.denomination_code_stamp,
        "marginalia": schedule.marginalia,
        "ai_notes": schedule.ai_notes,
    }
    bodies = []
    for body in sorted(schedule.church_details.all(), key=lambda item: item.pk):
        body_data = {"id": body.pk}
        body_data.update(
            {
                field: _json_value(getattr(body, field))
                for field in BODY_FIELDS
            }
        )
        body_data["membership"] = []
        for membership in sorted(body.membership.all(), key=lambda item: item.pk):
            values = {"id": membership.pk}
            values.update(
                {
                    field: _json_value(getattr(membership, field))
                    for field in MEMBERSHIP_FIELDS
                }
            )
            body_data["membership"].append(values)
        bodies.append(body_data)

    clergy = []
    for person in sorted(schedule.clergy.all(), key=lambda item: item.pk):
        values = {"id": person.pk}
        values.update(
            {field: _json_value(getattr(person, field)) for field in CLERGY_FIELDS}
        )
        clergy.append(values)
    return {
        "schema_version": DECISION_VERSION,
        "schedule_fields": schedule_fields,
        "religious_bodies": bodies,
        "clergy": clergy,
    }


def canonical_fingerprint(snapshot):
    payload = json.dumps(
        snapshot,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_reconciliation_preview(
    schedule,
    transcription=None,
    *,
    decisions=None,
    mixed=False,
    validate=True,
):
    """Return the live baseline, proposed draft, and explicit consequences."""
    before = serialize_canonical(schedule)
    candidate = (
        before
        if transcription is None
        else _candidate_draft(schedule, transcription, before)
    )
    review = build_mixed_review(before, candidate, decisions or {})
    proposed = review["proposed"] if mixed else candidate
    if validate:
        _validate_draft(schedule, proposed)
    operations = _operation_summary(before, proposed)
    warnings = _consistency_warnings(proposed)
    comparison_counts = Counter(
        row["status"]
        for section in review["sections"]
        for row in section["rows"]
    )
    return {
        "before": before,
        "candidate": candidate,
        "proposed": proposed,
        "before_fingerprint": canonical_fingerprint(before),
        "operations": operations,
        "warnings": warnings,
        "has_changes": before != proposed,
        "review_sections": review["sections"],
        "decisions": review["decisions"],
        "decisions_fingerprint": decisions_fingerprint(review["decisions"]),
        "comparison": {
            "sections": review["sections"],
            "counts": {
                "same": comparison_counts["same"],
                "equivalent": comparison_counts["equivalent"],
                "different": comparison_counts["different"],
                "one_missing": comparison_counts["one_missing"],
                "blank_zero": comparison_counts["blank_zero"],
            },
        },
    }


def infer_reconciliation_outcome(preview):
    """Derive provenance from the reviewer-selected result."""
    if any(
        isinstance(decision, dict) and decision.get("source") == "edited"
        for decision in preview["decisions"].values()
    ):
        return ScheduleReconciliation.Outcome.MIXED
    if preview["proposed"] == preview["candidate"]:
        return ScheduleReconciliation.Outcome.PROMOTED_CANDIDATE
    if preview["proposed"] == preview["before"]:
        return ScheduleReconciliation.Outcome.RETAINED_CURRENT
    return ScheduleReconciliation.Outcome.MIXED


@transaction.atomic
def apply_reconciliation(
    *,
    schedule_id,
    reviewer,
    outcome,
    expected_fingerprint,
    transcription_id=None,
    notes="",
    decisions=None,
):
    """Apply one fully reviewed decision and approve the schedule atomically."""
    if outcome not in ScheduleReconciliation.Outcome.values:
        raise ReconciliationValidationError("Choose a valid reconciliation outcome.")
    if outcome in {
        ScheduleReconciliation.Outcome.PROMOTED_CANDIDATE,
        ScheduleReconciliation.Outcome.MIXED,
    }:
        if not transcription_id:
            raise ReconciliationValidationError("Choose a candidate to promote.")

    # Lock only the schedule row. The graph queryset joins nullable relations,
    # which PostgreSQL cannot include in an unrestricted FOR UPDATE clause.
    CensusSchedule.objects.select_for_update(of=("self",)).get(pk=schedule_id)
    schedule = schedule_graph_queryset().get(pk=schedule_id)
    transcription = None
    if transcription_id:
        transcription = (
            ScheduleTranscription.objects.select_related("run")
            .filter(census_schedule=schedule, pk=transcription_id)
            .first()
        )
        if transcription is None:
            raise ReconciliationValidationError(
                "The selected candidate does not belong to this schedule."
            )

    preview = build_reconciliation_preview(
        schedule,
        transcription
        if outcome
        in {
            ScheduleReconciliation.Outcome.PROMOTED_CANDIDATE,
            ScheduleReconciliation.Outcome.MIXED,
        }
        else None,
        decisions=(
            decisions
            if outcome == ScheduleReconciliation.Outcome.MIXED
            else None
        ),
        mixed=outcome == ScheduleReconciliation.Outcome.MIXED,
    )
    if preview["before_fingerprint"] != expected_fingerprint:
        raise StaleReconciliationError(
            "The canonical record changed after this preview. Refresh and review "
            "it again."
        )
    duplicate = ScheduleReconciliation.objects.filter(
        census_schedule=schedule,
        reviewer=reviewer,
        outcome=outcome,
        before_fingerprint=expected_fingerprint,
        sources__transcription_id=transcription_id,
    ).first()
    if duplicate:
        return duplicate

    if outcome in {
        ScheduleReconciliation.Outcome.PROMOTED_CANDIDATE,
        ScheduleReconciliation.Outcome.MIXED,
    }:
        _apply_draft(schedule, preview["proposed"], reviewer)
    _approve_schedule(schedule, reviewer)

    refreshed = schedule_graph_queryset().get(pk=schedule.pk)
    after = serialize_canonical(refreshed)
    reconciliation = ScheduleReconciliation.objects.create(
        census_schedule=refreshed,
        reviewer=reviewer,
        outcome=outcome,
        notes=notes.strip(),
        canonical_before=preview["before"],
        canonical_after=after,
        before_fingerprint=expected_fingerprint,
        after_fingerprint=canonical_fingerprint(after),
        decisions={
            "version": DECISION_VERSION,
            "starting_source": (
                f"transcription:{transcription.pk}"
                if outcome
                in {
                    ScheduleReconciliation.Outcome.PROMOTED_CANDIDATE,
                    ScheduleReconciliation.Outcome.MIXED,
                }
                else "current_canonical"
            ),
            "operations": preview["operations"],
            "field_source_decisions": (
                preview["decisions"]
                if outcome == ScheduleReconciliation.Outcome.MIXED
                else {}
            ),
            "reviewer_overrides": (
                [
                    {"field": key, **decision}
                    for key, decision in preview["decisions"].items()
                    if isinstance(decision, dict)
                    and decision.get("source") == "edited"
                ]
                if outcome == ScheduleReconciliation.Outcome.MIXED
                else []
            ),
        },
    )
    if transcription:
        disposition = (
            ReconciliationSource.Disposition.INCORPORATED
            if outcome == ScheduleReconciliation.Outcome.MIXED
            else (
                ReconciliationSource.Disposition.ACCEPTED
                if outcome == ScheduleReconciliation.Outcome.PROMOTED_CANDIDATE
                else ReconciliationSource.Disposition.REJECTED
            )
        )
        ReconciliationSource.objects.create(
            reconciliation=reconciliation,
            transcription=transcription,
            disposition=disposition,
        )
    return reconciliation


def _candidate_draft(schedule, transcription, before):
    data = deepcopy(transcription.data)
    if transcription.run.kind == "agent":
        version = transcription.run.metadata.get("contract_version")
        if version != CONTRACT_VERSION:
            raise ReconciliationValidationError(
                f"Unsupported candidate contract {version or 'unknown'!r}."
            )
        try:
            validate_candidate(
                data,
                schedule,
                schema=transcription.run.metadata.get("schema"),
            )
        except CandidateValidationError as exc:
            raise ReconciliationValidationError(str(exc)) from exc
    elif transcription.run.kind != "human_snapshot":
        raise ReconciliationValidationError(
            f"Unsupported transcription kind {transcription.run.kind!r}."
        )

    fields = data.get("schedule_fields") or {}
    respondent = fields.get("respondent") or {}
    processing = fields.get("processing") or {}
    proposed_fields = deepcopy(before["schedule_fields"])
    mappings = {
        "num_assistant_pastors": fields.get("num_assistant_pastors", _MISSING),
        "respondent_name": respondent.get(
            "name", fields.get("respondent_name", _MISSING)
        ),
        "respondent_title": respondent.get(
            "title", fields.get("respondent_title", _MISSING)
        ),
        "respondent_po_address": respondent.get(
            "po_address", fields.get("respondent_po_address", _MISSING)
        ),
        "respondent_date_signed": respondent.get(
            "date_signed", fields.get("respondent_date_signed", _MISSING)
        ),
        "date_received": processing.get(
            "date_received", fields.get("date_received", _MISSING)
        ),
        "district_stamp": processing.get(
            "district_stamp", fields.get("district_stamp", _MISSING)
        ),
        "denomination_code_stamp": processing.get(
            "denomination_code_stamp",
            fields.get("denomination_code_stamp", _MISSING),
        ),
        "marginalia": fields.get("marginalia", _MISSING),
        "ai_notes": fields.get("ai_notes", _MISSING),
        "populated_place_id": fields.get("populated_place_id", _MISSING),
    }
    for field, value in mappings.items():
        if value is not _MISSING:
            if field == "marginalia" and value is None:
                value = []
            proposed_fields[field] = value

    bodies = []
    for body in data.get("religious_bodies") or []:
        values = {field: body.get(field) for field in BODY_FIELDS}
        if body.get("id") is not None:
            values["id"] = body["id"]
        memberships = body.get("membership", [])
        if isinstance(memberships, dict):
            memberships = [memberships]
        values["membership"] = []
        for membership in memberships:
            member_values = {
                field: membership.get(field) for field in MEMBERSHIP_FIELDS
            }
            if membership.get("id") is not None:
                member_values["id"] = membership["id"]
            values["membership"].append(member_values)
        bodies.append(values)

    clergy = []
    for person in data.get("clergy") or []:
        values = {field: person.get(field) for field in CLERGY_FIELDS}
        if person.get("id") is not None:
            values["id"] = person["id"]
        clergy.append(values)
    return {
        "schema_version": DECISION_VERSION,
        "schedule_fields": proposed_fields,
        "religious_bodies": bodies,
        "clergy": clergy,
    }


def decisions_fingerprint(decisions):
    payload = json.dumps(
        decisions,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_mixed_review(before, candidate, decisions):
    """Align entities explicitly and construct a field-level mixed draft."""
    used_decisions = {}
    sections = []
    proposed_fields = {}
    for title, fields in SCHEDULE_FIELD_GROUPS:
        rows = []
        for field, label in fields:
            key = f"schedule.{field}"
            current_value = before["schedule_fields"].get(field)
            candidate_value = candidate["schedule_fields"].get(field)
            proposed_fields[field] = _selected_value(
                decisions,
                used_decisions,
                key,
                current_value,
                candidate_value,
            )
            rows.append(
                comparison_row(
                    label,
                    current_value,
                    candidate_value,
                    decision_key=key,
                    edit_type=_edit_type(key),
                    **_decision_row_options(used_decisions[key]),
                )
            )
        sections.append(
            {
                "title": title,
                "note": (
                    "Select a value cell. Double-click it, or use Edit, to "
                    "enter a reviewer correction."
                ),
                "rows": rows,
                "decision_scope": "field",
            }
        )

    for title, fields in AI_CONTEXT_FIELD_GROUPS:
        rows = []
        for field, label in fields:
            current_value = before["schedule_fields"].get(field)
            candidate_value = candidate["schedule_fields"].get(field)
            proposed_fields[field] = deepcopy(candidate_value)
            rows.append(comparison_row(label, current_value, candidate_value))
        sections.append(
            {
                "title": title,
                "note": (
                    "AI transcription context is carried from the selected "
                    "evidence automatically."
                ),
                "rows": rows,
                "decision_scope": "automatic",
                "automatic_source": "candidate",
            }
        )

    proposed_bodies = []
    body_matches, current_only_bodies, candidate_only_bodies = (
        _match_snapshot_rows(
            before["religious_bodies"],
            candidate["religious_bodies"],
            signature_fields=("address", "census_code"),
            match_single=True,
        )
    )
    for current_body, candidate_body in sorted(
        body_matches, key=lambda pair: pair[0]["id"]
    ):
        token = f"body.{current_body['id']}"
        proposed_body, body_sections = _mixed_body(
            token,
            current_body,
            candidate_body,
            decisions,
            used_decisions,
        )
        proposed_bodies.append(proposed_body)
        sections.extend(body_sections)

    for current_body in sorted(
        current_only_bodies, key=lambda row: row["id"]
    ):
        token = f"body.{current_body['id']}"
        key = f"entity.{token}"
        selected = _selected_source(decisions, used_decisions, key)
        if selected == "current":
            proposed_bodies.append(deepcopy(current_body))
        sections.append(
            _entity_section(
                f"Religious body: {current_body.get('name') or current_body['id']}",
                current_body,
                None,
                BODY_FIELDS,
                BODY_LABELS,
                key,
                selected,
                "Retain current body",
                "Remove body",
                note=(
                    f"Current-only body with "
                    f"{len(current_body.get('membership', []))} membership row(s)."
                ),
            )
        )

    candidate_body_indices = {
        id(row): index for index, row in enumerate(candidate["religious_bodies"])
    }
    for candidate_body in candidate_only_bodies:
        index = candidate_body_indices[id(candidate_body)]
        token = f"body.new.{index}"
        key = f"entity.{token}"
        selected = _selected_source(decisions, used_decisions, key)
        if selected == "candidate":
            proposed_body = deepcopy(candidate_body)
            proposed_body["_force_create"] = True
            proposed_bodies.append(proposed_body)
        sections.append(
            _entity_section(
                f"Candidate religious body: "
                f"{candidate_body.get('name') or index + 1}",
                None,
                candidate_body,
                BODY_FIELDS,
                BODY_LABELS,
                key,
                selected,
                "Do not add body",
                "Add candidate body",
                note=(
                    f"Candidate-only body with "
                    f"{len(candidate_body.get('membership', []))} membership row(s)."
                ),
            )
        )

    proposed_clergy = []
    clergy_matches, current_only_clergy, candidate_only_clergy = (
        _match_snapshot_rows(
            before["clergy"],
            candidate["clergy"],
            signature_fields=("name", "is_assistant"),
        )
    )
    for current_person, candidate_person in sorted(
        clergy_matches, key=lambda pair: pair[0]["id"]
    ):
        token = f"clergy.{current_person['id']}"
        proposed_person, section = _mixed_matched_entity(
            token,
            f"Clergy: {current_person.get('name') or current_person['id']}",
            current_person,
            candidate_person,
            CLERGY_FIELDS,
            CLERGY_LABELS,
            decisions,
            used_decisions,
        )
        proposed_clergy.append(proposed_person)
        sections.append(section)

    for current_person in sorted(
        current_only_clergy, key=lambda row: row["id"]
    ):
        token = f"clergy.{current_person['id']}"
        key = f"entity.{token}"
        selected = _selected_source(decisions, used_decisions, key)
        if selected == "current":
            proposed_clergy.append(deepcopy(current_person))
        sections.append(
            _entity_section(
                f"Clergy: {current_person.get('name') or current_person['id']}",
                current_person,
                None,
                CLERGY_FIELDS,
                CLERGY_LABELS,
                key,
                selected,
                "Retain current clergy row",
                "Remove clergy row",
            )
        )

    candidate_clergy_indices = {
        id(row): index for index, row in enumerate(candidate["clergy"])
    }
    for candidate_person in candidate_only_clergy:
        index = candidate_clergy_indices[id(candidate_person)]
        token = f"clergy.new.{index}"
        key = f"entity.{token}"
        selected = _selected_source(decisions, used_decisions, key)
        if selected == "candidate":
            proposed_person = deepcopy(candidate_person)
            proposed_person["_force_create"] = True
            proposed_clergy.append(proposed_person)
        sections.append(
            _entity_section(
                f"Candidate clergy: {candidate_person.get('name') or index + 1}",
                None,
                candidate_person,
                CLERGY_FIELDS,
                CLERGY_LABELS,
                key,
                selected,
                "Do not add clergy row",
                "Add candidate clergy row",
            )
        )

    return {
        "proposed": {
            "schema_version": DECISION_VERSION,
            "schedule_fields": proposed_fields,
            "religious_bodies": proposed_bodies,
            "clergy": proposed_clergy,
        },
        "sections": sections,
        "decisions": used_decisions,
    }


def _mixed_body(
    token,
    current_body,
    candidate_body,
    decisions,
    used_decisions,
):
    proposed_body, body_section = _mixed_matched_entity(
        token,
        f"Religious body: {current_body.get('name') or current_body['id']}",
        current_body,
        candidate_body,
        BODY_FIELDS,
        BODY_LABELS,
        decisions,
        used_decisions,
    )
    memberships = []
    membership_sections = []
    matches, current_only, candidate_only = _match_snapshot_rows(
        current_body.get("membership", []),
        candidate_body.get("membership", []),
        signature_fields=MEMBERSHIP_FIELDS,
        match_single=True,
    )
    for current_membership, candidate_membership in sorted(
        matches, key=lambda pair: pair[0]["id"]
    ):
        member_token = f"membership.{current_membership['id']}"
        proposed_membership, section = _mixed_matched_entity(
            member_token,
            f"{body_section['title']}: membership {current_membership['id']}",
            current_membership,
            candidate_membership,
            MEMBERSHIP_FIELDS,
            MEMBERSHIP_LABELS,
            decisions,
            used_decisions,
        )
        memberships.append(proposed_membership)
        membership_sections.append(section)
    for current_membership in sorted(current_only, key=lambda row: row["id"]):
        member_token = f"membership.{current_membership['id']}"
        key = f"entity.{member_token}"
        selected = _selected_source(decisions, used_decisions, key)
        if selected == "current":
            memberships.append(deepcopy(current_membership))
        membership_sections.append(
            _entity_section(
                f"{body_section['title']}: membership {current_membership['id']}",
                current_membership,
                None,
                MEMBERSHIP_FIELDS,
                MEMBERSHIP_LABELS,
                key,
                selected,
                "Retain current membership",
                "Remove membership",
            )
        )
    candidate_indices = {
        id(row): index
        for index, row in enumerate(candidate_body.get("membership", []))
    }
    for candidate_membership in candidate_only:
        index = candidate_indices[id(candidate_membership)]
        member_token = f"{token}.membership.new.{index}"
        key = f"entity.{member_token}"
        selected = _selected_source(decisions, used_decisions, key)
        if selected == "candidate":
            proposed_membership = deepcopy(candidate_membership)
            proposed_membership["_force_create"] = True
            memberships.append(proposed_membership)
        membership_sections.append(
            _entity_section(
                f"{body_section['title']}: candidate membership {index + 1}",
                None,
                candidate_membership,
                MEMBERSHIP_FIELDS,
                MEMBERSHIP_LABELS,
                key,
                selected,
                "Do not add membership",
                "Add candidate membership",
            )
        )
    proposed_body["membership"] = memberships
    return proposed_body, [body_section, *membership_sections]


def _mixed_matched_entity(
    token,
    title,
    current,
    candidate,
    fields,
    labels,
    decisions,
    used_decisions,
):
    proposed = {"id": current["id"]}
    rows = []
    for field in fields:
        key = f"{token}.{field}"
        proposed[field] = _selected_value(
            decisions,
            used_decisions,
            key,
            current.get(field),
            candidate.get(field),
        )
        rows.append(
            comparison_row(
                labels[field],
                current.get(field),
                candidate.get(field),
                decision_key=key,
                edit_type=_edit_type(key),
                **_decision_row_options(used_decisions[key]),
            )
        )
    return proposed, {
        "title": title,
        "note": (
            "Matched without relying on database or array order. Select a "
            "value cell, or edit the selected value."
        ),
        "rows": rows,
        "decision_scope": "field",
    }


def _entity_section(
    title,
    current,
    candidate,
    fields,
    labels,
    key,
    selected,
    current_label,
    candidate_label,
    note="",
):
    current = current or {}
    candidate = candidate or {}
    return {
        "title": title,
        "note": note or "Choose explicitly whether this unmatched row is retained.",
        "rows": [
            comparison_row(
                labels[field],
                current.get(field, MISSING),
                candidate.get(field, MISSING),
            )
            for field in fields
        ],
        "decision_scope": "entity",
        "entity_decision": {
            "key": key,
            "selected": selected,
            "current_label": current_label,
            "candidate_label": candidate_label,
        },
    }


def _selected_source(decisions, used_decisions, key):
    selected = decisions.get(key, "candidate")
    if selected not in {"current", "candidate"}:
        raise ReconciliationValidationError(
            f"Invalid source decision for {key!r}."
        )
    used_decisions[key] = selected
    return selected


def _selected_value(
    decisions,
    used_decisions,
    key,
    current_value,
    candidate_value,
):
    decision = decisions.get(key, "candidate")
    if isinstance(decision, dict):
        if decision.get("source") != "edited":
            raise ReconciliationValidationError(
                f"Invalid source decision for {key!r}."
            )
        base = decision.get("base")
        if base not in {"current", "candidate"}:
            raise ReconciliationValidationError(
                f"Choose the source value used to edit {key!r}."
            )
        value = _coerce_edited_value(key, decision.get("value", ""))
        used_decisions[key] = {
            "source": "edited",
            "base": base,
            "value": value,
        }
        return deepcopy(value)

    selected = _selected_source(decisions, used_decisions, key)
    return deepcopy(current_value if selected == "current" else candidate_value)


def _decision_row_options(decision):
    if isinstance(decision, dict):
        return {
            "selected": "edited",
            "edited_base": decision["base"],
            "edited_value": decision["value"],
        }
    return {"selected": decision}


def _edit_type(key):
    field = key.rsplit(".", 1)[-1]
    if field in BOOLEAN_FIELDS:
        return "boolean"
    if field in DATE_FIELDS:
        return "date"
    if field in DECIMAL_FIELDS:
        return "decimal"
    if field in INTEGER_FIELDS:
        return "integer"
    return "text"


def _coerce_edited_value(key, raw_value):
    field = key.rsplit(".", 1)[-1]
    value = "" if raw_value is None else str(raw_value).strip()
    if field in INTEGER_FIELDS:
        if value == "":
            return None
        try:
            return int(value)
        except ValueError as exc:
            raise ReconciliationValidationError(
                f"Enter a whole number for {key!r}."
            ) from exc
    if field in DECIMAL_FIELDS:
        if value == "":
            return None
        try:
            decimal_value = Decimal(value)
        except InvalidOperation as exc:
            raise ReconciliationValidationError(
                f"Enter a number for {key!r}."
            ) from exc
        if not decimal_value.is_finite():
            raise ReconciliationValidationError(
                f"Enter a finite number for {key!r}."
            )
        return format(decimal_value, "f")
    if field in BOOLEAN_FIELDS:
        if value == "":
            return None
        normalized = value.casefold()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False
        raise ReconciliationValidationError(
            f"Choose Yes, No, or Blank for {key!r}."
        )
    if field in DATE_FIELDS:
        if value == "":
            return None
        return _parse_date(value).isoformat()
    return value


def _validate_draft(schedule, draft):
    if not draft["religious_bodies"]:
        raise ReconciliationValidationError(
            "A canonical schedule must contain at least one religious body."
        )
    fields = draft["schedule_fields"]
    place_id = fields.get("populated_place_id")
    place = None
    if place_id is not None:
        if schedule.county_id is None:
            raise ReconciliationValidationError(
                "A populated place cannot be selected without a schedule county."
            )
        place = PopulatedPlace.objects.filter(
            county=schedule.county, place_id=place_id
        ).first()
        if place is None:
            raise ReconciliationValidationError(
                "The proposed populated place is not in the schedule county."
            )

    candidate_schedule = CensusSchedule.objects.get(pk=schedule.pk)
    candidate_schedule.populated_place = place
    for field in SCHEDULE_FIELDS:
        value = fields.get(field)
        if field in {
            "respondent_name",
            "respondent_title",
            "respondent_po_address",
            "respondent_date_signed",
            "district_stamp",
            "denomination_code_stamp",
            "ai_notes",
        } and value is None:
            value = ""
        if field == "date_received":
            value = _parse_date(value)
        _reject_negative(field, value)
        setattr(candidate_schedule, field, value)
    _full_clean(candidate_schedule)

    for body_data in draft["religious_bodies"]:
        body = ReligiousBody(
            census_record=schedule,
            denomination=schedule.schedule_denomination,
            **{field: body_data.get(field) for field in BODY_FIELDS},
        )
        for field in BODY_FIELDS:
            _reject_negative(field, getattr(body, field))
        _full_clean(body, exclude={"id"})
        for membership_data in body_data["membership"]:
            membership = Membership(
                census_record=schedule,
                religious_body=body,
                **{
                    field: membership_data.get(field)
                    for field in MEMBERSHIP_FIELDS
                },
            )
            for field in MEMBERSHIP_FIELDS:
                _reject_negative(field, getattr(membership, field))
            _full_clean(membership, exclude={"id", "religious_body"})
    for person_data in draft["clergy"]:
        person = Clergy(
            census_schedule=schedule,
            **{field: person_data.get(field) for field in CLERGY_FIELDS},
        )
        _reject_negative(
            "num_other_churches_served", person.num_other_churches_served
        )
        _full_clean(person, exclude={"id"})


def _apply_draft(schedule, draft, reviewer):
    fields = draft["schedule_fields"]
    place_id = fields.get("populated_place_id")
    schedule.populated_place = (
        PopulatedPlace.objects.get(county=schedule.county, place_id=place_id)
        if place_id is not None
        else None
    )
    for field in SCHEDULE_FIELDS:
        value = fields.get(field)
        if field in {
            "respondent_name",
            "respondent_title",
            "respondent_po_address",
            "respondent_date_signed",
            "district_stamp",
            "denomination_code_stamp",
            "ai_notes",
        } and value is None:
            value = ""
        if field == "date_received":
            value = _parse_date(value)
        setattr(schedule, field, value)
    _history_save(schedule, reviewer, "Applied schedule reconciliation")

    body_matches, removed_bodies, added_bodies = _match_rows(
        list(schedule.church_details.all()),
        draft["religious_bodies"],
        signature_fields=("address", "census_code"),
        match_single=True,
    )
    for body, body_data in body_matches:
        old_address = body.address
        for field in BODY_FIELDS:
            setattr(body, field, body_data.get(field))
        if old_address != body.address:
            body.latitude = None
            body.longitude = None
            body.geocode_status = "pending" if body.address else "skipped"
            body.geocoded_at = None
        _history_save(body, reviewer, "Applied schedule reconciliation")
        _apply_memberships(schedule, body, body_data["membership"], reviewer)

    for body in removed_bodies:
        for membership in body.membership.all():
            _history_delete(membership, reviewer, "Applied schedule reconciliation")
        _history_delete(body, reviewer, "Applied schedule reconciliation")

    for body_data in added_bodies:
        body = ReligiousBody(
            census_record=schedule,
            denomination=schedule.schedule_denomination,
            **{field: body_data.get(field) for field in BODY_FIELDS},
        )
        body.geocode_status = "pending" if body.address else "skipped"
        _history_save(body, reviewer, "Applied schedule reconciliation")
        for membership_data in body_data["membership"]:
            membership = Membership(
                census_record=schedule,
                religious_body=body,
                **{
                    field: membership_data.get(field)
                    for field in MEMBERSHIP_FIELDS
                },
            )
            _history_save(membership, reviewer, "Applied schedule reconciliation")

    clergy_matches, removed_clergy, added_clergy = _match_rows(
        list(schedule.clergy.all()),
        draft["clergy"],
        signature_fields=("name", "is_assistant"),
    )
    for person, person_data in clergy_matches:
        for field in CLERGY_FIELDS:
            setattr(person, field, person_data.get(field))
        _history_save(person, reviewer, "Applied schedule reconciliation")
    for person in removed_clergy:
        _history_delete(person, reviewer, "Applied schedule reconciliation")
    for person_data in added_clergy:
        person = Clergy(
            census_schedule=schedule,
            **{field: person_data.get(field) for field in CLERGY_FIELDS},
        )
        _history_save(person, reviewer, "Applied schedule reconciliation")


def _apply_memberships(schedule, body, proposed, reviewer):
    matches, removed, added = _match_rows(
        list(body.membership.all()),
        proposed,
        signature_fields=MEMBERSHIP_FIELDS,
        match_single=True,
    )
    for membership, membership_data in matches:
        for field in MEMBERSHIP_FIELDS:
            setattr(membership, field, membership_data.get(field))
        membership.census_record = schedule
        _history_save(membership, reviewer, "Applied schedule reconciliation")
    for membership in removed:
        _history_delete(membership, reviewer, "Applied schedule reconciliation")
    for membership_data in added:
        membership = Membership(
            census_record=schedule,
            religious_body=body,
            **{
                field: membership_data.get(field) for field in MEMBERSHIP_FIELDS
            },
        )
        _history_save(membership, reviewer, "Applied schedule reconciliation")


def _approve_schedule(schedule, reviewer):
    if schedule.transcription_status != "approved":
        schedule.transcription_status = "approved"
        _history_save(schedule, reviewer, "Approved through schedule reconciliation")


def _match_rows(current, proposed, *, signature_fields, match_single=False):
    """Match only by owned IDs or unique signatures; never by list order."""
    remaining_current = {item.pk: item for item in current}
    remaining_proposed = list(proposed)
    matches = []

    for proposed_row in list(remaining_proposed):
        if proposed_row.get("_force_create"):
            continue
        row_id = proposed_row.get("id")
        if row_id in remaining_current:
            matches.append((remaining_current.pop(row_id), proposed_row))
            remaining_proposed.remove(proposed_row)

    if (
        match_single
        and len(remaining_current) == len(remaining_proposed) == 1
        and not remaining_proposed[0].get("_force_create")
    ):
        current_row = next(iter(remaining_current.values()))
        proposed_row = remaining_proposed.pop()
        matches.append((current_row, proposed_row))
        remaining_current.pop(current_row.pk)

    current_by_signature = _unique_signatures(
        remaining_current.values(),
        lambda item: tuple(getattr(item, field) for field in signature_fields),
    )
    proposed_by_signature = _unique_signatures(
        [row for row in remaining_proposed if not row.get("_force_create")],
        lambda item: tuple(item.get(field) for field in signature_fields),
    )
    shared_signatures = current_by_signature.keys() & proposed_by_signature.keys()
    for signature in sorted(shared_signatures, key=repr):
        current_row = current_by_signature[signature]
        proposed_row = proposed_by_signature[signature]
        matches.append((current_row, proposed_row))
        remaining_current.pop(current_row.pk)
        remaining_proposed.remove(proposed_row)
    return matches, list(remaining_current.values()), remaining_proposed


def _unique_signatures(rows, signature):
    rows = list(rows)
    counts = Counter(signature(row) for row in rows)
    return {signature(row): row for row in rows if counts[signature(row)] == 1}


def _operation_summary(before, proposed):
    changed_fields = []
    for field, value in proposed["schedule_fields"].items():
        if before["schedule_fields"].get(field) != value:
            changed_fields.append(field)

    body_matches, removed_bodies, added_bodies = _match_snapshot_rows(
        before["religious_bodies"],
        proposed["religious_bodies"],
        signature_fields=("address", "census_code"),
        match_single=True,
    )
    geocoding_resets = sum(
        old.get("address") != new.get("address") for old, new in body_matches
    ) + sum(bool(body.get("address")) for body in added_bodies)
    membership_counts = {"updated": 0, "added": 0, "removed": 0}
    for old_body, new_body in body_matches:
        member_matches, removed_members, added_members = _match_snapshot_rows(
            old_body.get("membership", []),
            new_body.get("membership", []),
            signature_fields=MEMBERSHIP_FIELDS,
            match_single=True,
        )
        membership_counts["updated"] += sum(
            _fields_changed(old, new, MEMBERSHIP_FIELDS)
            for old, new in member_matches
        )
        membership_counts["added"] += len(added_members)
        membership_counts["removed"] += len(removed_members)
    membership_counts["removed"] += sum(
        len(body.get("membership", [])) for body in removed_bodies
    )
    membership_counts["added"] += sum(
        len(body.get("membership", [])) for body in added_bodies
    )
    clergy_matches, removed_clergy, added_clergy = _match_snapshot_rows(
        before["clergy"],
        proposed["clergy"],
        signature_fields=("name", "is_assistant"),
    )
    return {
        "schedule_fields_changed": changed_fields,
        "religious_bodies": {
            "updated": sum(
                _fields_changed(old, new, BODY_FIELDS)
                for old, new in body_matches
            ),
            "added": len(added_bodies),
            "removed": len(removed_bodies),
        },
        "memberships": membership_counts,
        "clergy": {
            "updated": sum(
                _fields_changed(old, new, CLERGY_FIELDS)
                for old, new in clergy_matches
            ),
            "added": len(added_clergy),
            "removed": len(removed_clergy),
        },
        "geocoding_resets": geocoding_resets,
    }


def _fields_changed(old, new, fields):
    return any(old.get(field) != new.get(field) for field in fields)


def _match_snapshot_rows(
    current, proposed, *, signature_fields, match_single=False
):
    class SnapshotRow:
        def __init__(self, data):
            self.data = data
            self.pk = data.get("id")

        def __getattr__(self, field):
            return self.data.get(field)

    matches, removed, added = _match_rows(
        [SnapshotRow(row) for row in current],
        proposed,
        signature_fields=signature_fields,
        match_single=match_single,
    )
    return (
        [(old.data, new) for old, new in matches],
        [old.data for old in removed],
        added,
    )


def _consistency_warnings(draft):
    warnings = []
    for body_index, body in enumerate(draft["religious_bodies"], start=1):
        if _sum_disagrees(
            body.get("expenses"),
            body.get("benevolences"),
            body.get("total_expenditures"),
        ):
            warnings.append(
                f"Religious body {body_index}: expenses plus benevolences does "
                "not equal total expenditures."
            )
        for membership_index, membership in enumerate(
            body["membership"], start=1
        ):
            prefix = f"Religious body {body_index}, membership {membership_index}"
            if _sum_disagrees(
                membership.get("male_members"),
                membership.get("female_members"),
                membership.get("total_members_by_sex"),
            ):
                warnings.append(f"{prefix}: sex subtotals do not equal the total.")
            if _sum_disagrees(
                membership.get("members_under_13"),
                membership.get("members_13_and_older"),
                membership.get("total_members_by_age"),
            ):
                warnings.append(f"{prefix}: age subtotals do not equal the total.")
    return warnings


def _sum_disagrees(left, right, total):
    if None in (left, right, total):
        return False
    try:
        return Decimal(str(left)) + Decimal(str(right)) != Decimal(str(total))
    except (InvalidOperation, TypeError, ValueError):
        return False


def _history_save(instance, reviewer, reason):
    instance._history_user = reviewer
    instance._change_reason = reason
    instance.full_clean()
    instance.save()


def _history_delete(instance, reviewer, reason):
    instance._history_user = reviewer
    instance._change_reason = reason
    instance.delete()


def _full_clean(instance, exclude=None):
    try:
        instance.full_clean(exclude=exclude or set())
    except ValidationError as exc:
        raise ReconciliationValidationError(str(exc)) from exc


def _reject_negative(field, value):
    if field not in NONNEGATIVE_FIELDS or value is None:
        return
    try:
        is_negative = Decimal(str(value)) < 0
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ReconciliationValidationError(
            f"{field} must be numeric or blank."
        ) from exc
    if is_negative:
        raise ReconciliationValidationError(f"{field} cannot be negative.")


def _parse_date(value):
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ReconciliationValidationError(
            "date_received must be an ISO date (YYYY-MM-DD)."
        ) from exc


def _json_value(value):
    if hasattr(value, "as_tuple"):
        return str(value)
    return value


_MISSING = object()
