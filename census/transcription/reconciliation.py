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
    choice_row,
)
from census.transcription.contracts import (
    CONTRACT_VERSION,
    CandidateValidationError,
    validate_candidate,
)
from location.models import PopulatedPlace

DECISION_VERSION = "schedule-reconciliation-v5"
CANONICAL = "canonical"
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
)  # serving_congregation is not on the 1926 form; reconciliation leaves it alone.
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
}
INTEGER_FIELDS = (NONNEGATIVE_FIELDS - DECIMAL_FIELDS) | {"populated_place_id"}
DATE_FIELDS = {"date_received"}
TEXT_FIELDS = {
    "respondent_name",
    "respondent_title",
    "respondent_po_address",
    "respondent_date_signed",
    "district_stamp",
    "denomination_code_stamp",
    "ai_notes",
}
SCHEDULE_FIELD_GROUPS = (
    (
        "Schedule",
        (
            ("populated_place_id", "City, town, village, etc."),
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
    return _normalize_snapshot(
        {
            "schema_version": DECISION_VERSION,
            "schedule_fields": schedule_fields,
            "religious_bodies": bodies,
            "clergy": clergy,
        }
    )


def _normalize_snapshot(snapshot):
    """Coerce every draft to its stored representation so comparisons are exact."""
    fields = snapshot["schedule_fields"]
    for field in TEXT_FIELDS:
        if fields.get(field) is None:
            fields[field] = ""
    for body in snapshot["religious_bodies"]:
        for field in DECIMAL_FIELDS:
            body[field] = _decimal_text(body.get(field))
    return snapshot


def _decimal_text(value):
    if value in (None, ""):
        return None
    try:
        return format(Decimal(str(value)).quantize(Decimal("0.01")), "f")
    except (InvalidOperation, TypeError, ValueError):
        return value


def canonical_unchanged_since(schedule, reconciliation):
    """Whether ``schedule`` still holds the data ``reconciliation`` produced.

    ``schedule`` must come from ``schedule_graph_queryset``. Only fields present
    in both snapshots are compared and ``schema_version`` is ignored, so a
    serializer change alone never reads as a human edit.
    """
    return _same_shared_fields(
        serialize_canonical(schedule), reconciliation.canonical_after
    )


def _same_shared_fields(current, stored):
    if isinstance(current, dict) and isinstance(stored, dict):
        return all(
            _same_shared_fields(current[key], stored[key])
            for key in current.keys() & stored.keys()
            if key != "schema_version"
        )
    if isinstance(current, list) and isinstance(stored, list):
        return len(current) == len(stored) and all(
            map(_same_shared_fields, current, stored)
        )
    return current == stored


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
    transcriptions=(),
    *,
    decisions=None,
    mixed=False,
    validate=True,
):
    """Return the live record, every source's draft, the proposed draft, and
    explicit consequences.

    The current canonical record anchors the review and every transcription is
    aligned against it. The first usable transcription is the primary source:
    each field and row follows it unless the reviewer decides otherwise, so an
    unmixed preview promotes it whole.
    """
    before = serialize_canonical(schedule)
    sources = {}
    source_errors = {}
    for transcription in transcriptions:
        try:
            sources[str(transcription.pk)] = _candidate_draft(
                schedule, transcription, before
            )
        except ReconciliationValidationError as exc:
            source_errors[str(transcription.pk)] = str(exc)
    if transcriptions and not sources:
        raise ReconciliationValidationError(next(iter(source_errors.values())))
    sources[CANONICAL] = before
    review = build_mixed_review(sources, decisions or {})
    proposed = review["proposed"] if mixed else next(iter(sources.values()))
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
        "sources": sources,
        "source_errors": source_errors,
        "proposed": proposed,
        "before_fingerprint": canonical_fingerprint(before),
        "operations": operations,
        "warnings": warnings,
        "has_changes": _source_content(before) != _source_content(proposed),
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
    if _source_content(preview["proposed"]) == _source_content(preview["before"]):
        return ScheduleReconciliation.Outcome.RETAINED_CURRENT
    if any(
        _source_content(preview["proposed"]) == _source_content(source)
        for source in preview["sources"].values()
    ):
        return ScheduleReconciliation.Outcome.PROMOTED_CANDIDATE
    return ScheduleReconciliation.Outcome.MIXED


@transaction.atomic
def apply_reconciliation(
    *,
    schedule_id,
    reviewer,
    expected_fingerprint,
    transcription_ids=(),
    notes="",
    decisions=None,
    approve=True,
    allow_removals=True,
):
    """Apply one fully reviewed decision atomically.

    ``transcription_ids`` are the sources the reviewer saw, primary first.
    Reviewers approve the schedule. Transcribers (``approve=False``) submit it
    as ``completed`` for review and may not remove existing rows.
    """
    # Lock only the schedule row. The graph queryset joins nullable relations,
    # which PostgreSQL cannot include in an unrestricted FOR UPDATE clause.
    CensusSchedule.objects.select_for_update(of=("self",)).get(pk=schedule_id)
    schedule = schedule_graph_queryset().get(pk=schedule_id)
    transcriptions = _reconciliation_transcriptions(schedule, transcription_ids)
    preview = build_reconciliation_preview(
        schedule,
        transcriptions,
        decisions=decisions,
        mixed=True,
    )
    if preview["before_fingerprint"] != expected_fingerprint:
        raise StaleReconciliationError(
            "The canonical record changed after this preview. Refresh and review "
            "it again."
        )
    source_refs = [_source_ref(transcription) for transcription in transcriptions]
    operations = preview["operations"]
    if not allow_removals and any(
        operations[group]["removed"]
        for group in ("religious_bodies", "memberships", "clergy")
    ):
        raise ReconciliationValidationError(
            "Transcribers cannot remove existing religious bodies, memberships, "
            "or clergy. Keep those rows and describe the problem in the notes."
        )
    outcome = infer_reconciliation_outcome(preview)
    if outcome in {
        ScheduleReconciliation.Outcome.PROMOTED_CANDIDATE,
        ScheduleReconciliation.Outcome.MIXED,
    }:
        _apply_draft(schedule, preview["proposed"], reviewer)
    if approve:
        approve_schedule(schedule, reviewer)
    else:
        # Query directly: schedule.church_details is prefetched and stale here.
        if not ReligiousBody.objects.filter(census_record=schedule).exists():
            raise ReconciliationValidationError(
                "Add at least one religious body before submitting for review."
            )
        schedule.transcription_status = "completed"
        _history_save(schedule, reviewer, "Submitted through schedule reconciliation")

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
            "source_refs": source_refs,
            "operations": preview["operations"],
            "field_source_decisions": preview["decisions"],
            "reviewer_overrides": [
                {"field": key, **decision}
                for key, decision in preview["decisions"].items()
                if isinstance(decision, dict)
                and decision.get("source") == "edited"
            ],
        },
    )
    for transcription in transcriptions:
        snapshot = preview["sources"].get(str(transcription.pk))
        if snapshot is None:
            # Unusable (e.g. an unsupported contract); reviewed all the same.
            disposition = ReconciliationSource.Disposition.REJECTED
        elif _source_content(preview["proposed"]) == _source_content(snapshot):
            disposition = ReconciliationSource.Disposition.ACCEPTED
        elif outcome == ScheduleReconciliation.Outcome.MIXED:
            disposition = ReconciliationSource.Disposition.INCORPORATED
        else:
            disposition = ReconciliationSource.Disposition.REJECTED
        ReconciliationSource.objects.create(
            reconciliation=reconciliation,
            transcription=transcription,
            disposition=disposition,
        )

    # Every run on offer when the reviewer submitted counts as reviewed,
    # whether or not it was one of the two compared; only runs that arrive
    # later stay pending.
    pending_candidates = ScheduleTranscription.objects.filter(
        census_schedule=schedule,
        run__kind="agent",
        reconciliation_sources__isnull=True,
    )
    for candidate in pending_candidates:
        ReconciliationSource.objects.create(
            reconciliation=reconciliation,
            transcription=candidate,
            disposition=ReconciliationSource.Disposition.SUPERSEDED,
        )
    return reconciliation


def latest_reversible_reconciliation(schedule, snapshot=None):
    """Return the newest unreversed event that produced the current data state."""
    snapshot = snapshot or serialize_canonical(schedule)
    events = schedule.reconciliations.filter(
        reverses__isnull=True,
        reversals__isnull=True,
    )
    for event in events.iterator():
        if _source_content(event.canonical_before) == _source_content(
            event.canonical_after
        ):
            continue
        if _source_content(event.canonical_after) == _source_content(snapshot):
            return event
    return None


@transaction.atomic
def rollback_reconciliation(
    *,
    schedule_id,
    reviewer,
    expected_fingerprint,
    reconciliation_id=None,
    notes="",
):
    """Restore an earlier canonical graph and preserve the reversal as evidence."""
    CensusSchedule.objects.select_for_update(of=("self",)).get(pk=schedule_id)
    schedule = schedule_graph_queryset().get(pk=schedule_id)
    before = serialize_canonical(schedule)
    before_fingerprint = canonical_fingerprint(before)
    if before_fingerprint != expected_fingerprint:
        raise StaleReconciliationError(
            "The canonical record changed after rollback was requested. "
            "Refresh and try again."
        )

    if reconciliation_id is None:
        target = latest_reversible_reconciliation(schedule, before)
    else:
        target = (
            schedule.reconciliations.filter(
                pk=reconciliation_id,
                reverses__isnull=True,
                reversals__isnull=True,
            )
            .select_related("reviewer")
            .first()
        )
    if target is None:
        raise ReconciliationValidationError(
            "No previous canonical data state can be restored."
        )
    if _source_content(target.canonical_after) != _source_content(before):
        raise StaleReconciliationError(
            "This reconciliation no longer represents the current canonical "
            "data state."
        )

    restored = deepcopy(target.canonical_before)
    _validate_draft(schedule, restored)
    operations = _operation_summary(before, restored)
    _apply_draft(schedule, restored, reviewer)
    approve_schedule(schedule, reviewer)

    refreshed = schedule_graph_queryset().get(pk=schedule.pk)
    after = serialize_canonical(refreshed)
    reversal = ScheduleReconciliation.objects.create(
        census_schedule=refreshed,
        reviewer=reviewer,
        outcome=ScheduleReconciliation.Outcome.ROLLED_BACK,
        notes=notes.strip(),
        canonical_before=before,
        canonical_after=after,
        before_fingerprint=before_fingerprint,
        after_fingerprint=canonical_fingerprint(after),
        decisions={
            "version": DECISION_VERSION,
            "rollback_of": target.pk,
            "operations": operations,
        },
        reverses=target,
    )
    for source in target.sources.select_related("transcription"):
        ReconciliationSource.objects.create(
            reconciliation=reversal,
            transcription=source.transcription,
            disposition=ReconciliationSource.Disposition.SUPERSEDED,
        )
    return reversal


def _reconciliation_transcriptions(schedule, transcription_ids):
    ids = [int(pk) for pk in transcription_ids]
    found = ScheduleTranscription.objects.select_related("run").filter(
        census_schedule=schedule, pk__in=ids
    ).in_bulk()
    if len(found) != len(set(ids)):
        raise ReconciliationValidationError(
            "A selected source does not belong to this schedule."
        )
    return [found[pk] for pk in dict.fromkeys(ids)]


def _source_ref(transcription):
    return f"transcription:{transcription.pk}"


def _source_content(value):
    if isinstance(value, dict):
        return {
            key: _source_content(item)
            for key, item in value.items()
            if key not in {"id", "schema_version"} and not key.startswith("_")
        }
    if isinstance(value, list):
        return [_source_content(item) for item in value]
    return value


def _candidate_draft(schedule, transcription, before):
    data = deepcopy(transcription.data)
    if transcription.run.kind == "agent":
        version = transcription.run.metadata.get("contract_version")
        if version != CONTRACT_VERSION:
            raise ReconciliationValidationError(
                f"Unsupported candidate contract {version or 'unknown'!r}."
            )
        try:
            # Underscore keys carry non-contract evidence (e.g. bounding boxes).
            validate_candidate(
                {k: v for k, v in data.items() if not k.startswith("_")},
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
        # The 1926 form's only church location is line d ("City, town,
        # village, or township"), so the agent's body address is always
        # the verbatim place, blank when line d is blank.
        if transcription.run.kind == "agent":
            values["address"] = fields.get("populated_place_verbatim")
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
    return _normalize_snapshot(
        {
            "schema_version": DECISION_VERSION,
            "schedule_fields": proposed_fields,
            "religious_bodies": bodies,
            "clergy": clergy,
        }
    )


def decisions_fingerprint(decisions):
    payload = json.dumps(
        decisions,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_mixed_review(sources, decisions):
    """Align every source against the current record into one mixed draft.

    ``sources`` maps source refs to drafts, primary first, and includes the
    canonical record. A field decision names the source ref whose value is
    kept (or an edit based on one); a row that is not in every source also
    takes a keep/skip decision. Undecided fields and rows follow the primary.

    Section order follows the physical 1926 schedule form: Schedule fields,
    then religious bodies/clergy (the body of the form), then Respondent and
    Census Bureau processing (the form's footer), then AI context last.
    """
    review = _Review(sources, decisions)
    proposed_fields = {}
    sections = []
    schedule_title, schedule_fields = SCHEDULE_FIELD_GROUPS[0]
    sections.append(
        review.schedule_section(schedule_title, schedule_fields, proposed_fields)
    )

    proposed_bodies = []
    bodies = _align(
        review.order,
        lambda ref: _source_rows(ref, sources[ref]["religious_bodies"]),
        lambda anchors, rows: _match_snapshot_rows(
            anchors, rows, signature_fields=("address", "census_code"),
            match_single=True,
        ),
        "body",
        "body",
    )
    for number, (token, entry) in enumerate(bodies, start=1):
        title = f"Religious body: {_snapshot_label(_anchor(entry), number)}"
        body, section = review.entity(
            token, title, entry, BODY_FIELDS, BODY_LABELS, "body", "religious body"
        )
        sections.append(section)
        memberships = _align(
            list(entry),
            lambda ref: _source_rows(ref, entry[ref].get("membership", [])),
            lambda anchors, rows: _match_snapshot_rows(
                anchors, rows, signature_fields=MEMBERSHIP_FIELDS,
                match_single=True,
            ),
            "membership",
            f"{token}.membership",
        )
        kept_memberships = []
        for member_number, (member_token, member_entry) in enumerate(
            memberships, start=1
        ):
            membership, section = review.entity(
                member_token,
                f"{title}: membership {member_number}",
                member_entry,
                MEMBERSHIP_FIELDS,
                MEMBERSHIP_LABELS,
                "membership",
                "membership",
                scope=list(entry),
            )
            sections.append(section)
            if membership is not None:
                kept_memberships.append(membership)
        if body is not None:
            body["membership"] = kept_memberships
            proposed_bodies.append(body)

    # Clergy pair by position: a schedule holds at most one canonical pastor,
    # and sources list the pastor first, so row n meets row n. Extra rows are
    # new. A nameless source row is the model reading the blank assistant
    # lines as a person; drop it.
    proposed_clergy = []
    clergy = _align(
        review.order,
        lambda ref: (
            _source_rows(ref, sources[ref]["clergy"])
            if ref == CANONICAL
            else sorted(
                (row for row in sources[ref]["clergy"] if row.get("name")),
                key=lambda row: bool(row.get("is_assistant")),
            )
        ),
        _match_by_position,
        "clergy",
        "clergy",
    )
    for number, (token, entry) in enumerate(clergy, start=1):
        person, section = review.entity(
            token,
            f"Clergy: {_snapshot_label(_anchor(entry), number)}",
            entry,
            CLERGY_FIELDS,
            CLERGY_LABELS,
            "clergy",
            "clergy row",
        )
        sections.append(section)
        if person is not None:
            proposed_clergy.append(person)

    for title, fields in SCHEDULE_FIELD_GROUPS[1:]:
        sections.append(review.schedule_section(title, fields, proposed_fields))

    for title, fields in AI_CONTEXT_FIELD_GROUPS:
        section = review.schedule_section(title, fields, proposed_fields)
        for row in section["rows"]:
            row["can_edit"] = False
        section["decision_scope"] = "context"
        section["note"] = "Transcription notes, not form fields. Choose which to keep."
        sections.append(section)

    return {
        "proposed": {
            "schema_version": DECISION_VERSION,
            "schedule_fields": proposed_fields,
            "religious_bodies": proposed_bodies,
            "clergy": proposed_clergy,
        },
        "sections": sections,
        "decisions": review.used,
    }


class _Review:
    """Resolve reviewer decisions against sources in preference order."""

    def __init__(self, sources, decisions):
        self.sources = sources
        self.decisions = decisions
        self.used = {}
        self.primary = next(iter(sources))
        # Shown with the current record first, then the transcriptions.
        self.order = [CANONICAL, *(ref for ref in sources if ref != CANONICAL)]

    def default(self, refs, preferred=None):
        if preferred in refs:
            return preferred
        return next(ref for ref in self.sources if ref in refs)

    def choose(self, key, values, preferred=None):
        """Return the value chosen for ``key`` from ``{ref: value}``."""
        decision = self.decisions.get(key, self.default(values, preferred))
        if isinstance(decision, dict):
            if decision.get("source") != "edited":
                raise ReconciliationValidationError(
                    f"Invalid source decision for {key!r}."
                )
            if decision.get("base") not in values:
                raise ReconciliationValidationError(
                    f"Choose the source value used to edit {key!r}."
                )
            value = _coerce_edited_value(key, decision.get("value", ""))
            self.used[key] = {
                "source": "edited",
                "base": decision["base"],
                "value": value,
            }
            return deepcopy(value)
        if decision not in values:
            raise ReconciliationValidationError(
                f"Invalid source decision for {key!r}."
            )
        self.used[key] = decision
        value = values[decision]
        return None if value is MISSING else deepcopy(value)

    def row(self, label, key, field, values, complete=True):
        return choice_row(
            label,
            values,
            decision_key=key,
            complete=complete,
            edit_type=_edit_type(key),
            field=field,
            **_decision_row_options(self.used[key]),
        )

    def schedule_section(self, title, fields, proposed_fields):
        rows = []
        for field, label in fields:
            key = f"schedule.{field}"
            values = {
                ref: self.sources[ref]["schedule_fields"].get(field)
                for ref in self.order
            }
            proposed_fields[field] = self.choose(key, values)
            row = self.row(label, key, field, values)
            if field == "populated_place_id":
                _annotate_place_names(row)
            rows.append(row)
        return {
            "title": title,
            "note": "Select a source value, or type a reviewer correction.",
            "rows": rows,
            "decision_scope": "field",
            "kind": "schedule",
        }

    def entity(self, token, title, entry, fields, labels, kind, noun, scope=None):
        """Build one aligned row; return (proposed row or None, section).

        ``scope`` lists the sources the row could appear in (default: all).
        """
        scope = scope or list(self.sources)
        complete = all(ref in entry for ref in scope)
        anchor = _anchor(entry)
        proposed = {}
        if anchor.get("id") is not None:
            proposed["id"] = anchor["id"]
        rows = []
        for field in fields:
            key = f"{token}.{field}"
            preferred = None
            if kind == "body" and field == "address":
                # Line d as written is not shown on the review form; it follows
                # the source the reviewer chose for line d's matched place.
                place = self.used.get("schedule.populated_place_id")
                preferred = place["base"] if isinstance(place, dict) else place
            values = {ref: row.get(field, MISSING) for ref, row in entry.items()}
            proposed[field] = self.choose(key, values, preferred)
            rows.append(self.row(labels[field], key, field, values, complete))
        section = {
            "title": title,
            "note": "Select a source value, or type a reviewer correction.",
            "rows": rows,
            "decision_scope": "field",
            "kind": kind,
        }
        if complete:
            return proposed, section

        key = f"entity.{token}"
        selected = self.decisions.get(
            key, "keep" if self.default(scope) in entry else "skip"
        )
        if selected not in {"keep", "skip"}:
            raise ReconciliationValidationError(
                f"Invalid source decision for {key!r}."
            )
        self.used[key] = selected
        existing = CANONICAL in entry
        section["entity_decision"] = {
            "key": key,
            "selected": selected,
            "refs": list(entry),
            "keep_label": f"{'Keep' if existing else 'Add'} {noun}",
            "skip_label": f"{'Remove' if existing else 'Do not add'} {noun}",
        }
        if selected == "skip":
            return None, section
        if not existing:
            proposed["_force_create"] = anchor.get("id") is None
        return proposed, section


def _align(order, rows_of, match, canonical_prefix, new_prefix):
    """Group each source's rows into entities anchored on the current record.

    Returns ``[(token, {ref: row})]``. Canonical rows come first; a source row
    that matches no earlier entity starts a new one that later sources can
    match, so two models reading the same new row meet in one entity.
    """
    entities = []
    for ref in order:
        rows = rows_of(ref)
        indices = {id(row): index for index, row in enumerate(rows)}
        anchors = [_anchor(entry) for _, entry in entities]
        position = {id(row): index for index, row in enumerate(anchors)}
        matches, _, unmatched = match(anchors, rows)
        for anchor, row in matches:
            entities[position[id(anchor)]][1][ref] = row
        for row in unmatched:
            token = (
                f"{canonical_prefix}.{row['id']}"
                if ref == CANONICAL
                else f"{new_prefix}.new.{ref}.{indices[id(row)]}"
            )
            entities.append((token, {ref: row}))
    return entities


def _source_rows(ref, rows):
    return sorted(rows, key=_snapshot_sort_key) if ref == CANONICAL else list(rows)


def _match_by_position(anchors, rows):
    return list(zip(anchors, rows)), anchors[len(rows):], rows[len(anchors):]


def _anchor(entry):
    return next(iter(entry.values()))


def _annotate_place_names(row):
    """Show the place name and state after a bare Apiary place ID."""
    ids = {
        option["value"]
        for option in row["options"]
        if isinstance(option["value"], int)
    }
    if not ids:
        return
    names = {}
    for place in PopulatedPlace.objects.filter(place_id__in=ids).select_related(
        "county__state"
    ):
        names.setdefault(place.place_id, f"{place.name}, {place.county.state.code}")
    for option in row["options"]:
        if option["value"] in names:
            option["display"]["text"] = f"{option['value']} ({names[option['value']]})"


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
        return _decimal_text(decimal_value)
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
    place = _resolve_place(schedule, fields.get("populated_place_id"))

    candidate_schedule = CensusSchedule.objects.get(pk=schedule.pk)
    candidate_schedule.populated_place = place
    for field in SCHEDULE_FIELDS:
        value = fields.get(field)
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


def _resolve_place(schedule, place_id):
    if place_id is None:
        return None
    if schedule.county_id is None:
        raise ReconciliationValidationError(
            "A populated place cannot be selected without a schedule county."
        )
    places = list(
        PopulatedPlace.objects.filter(county=schedule.county, place_id=place_id)[:2]
    )
    if not places:
        raise ReconciliationValidationError(
            "The proposed populated place is not in the schedule county."
        )
    if len(places) > 1:
        raise ReconciliationValidationError(
            "The proposed populated place ID is ambiguous in the schedule county."
        )
    return places[0]


def _apply_draft(schedule, draft, reviewer):
    fields = draft["schedule_fields"]
    schedule.populated_place = _resolve_place(
        schedule, fields.get("populated_place_id")
    )
    for field in SCHEDULE_FIELDS:
        value = fields.get(field)
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
        match_single=True,
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


def approve_schedule(schedule, reviewer):
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
        match_single=True,
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
    remaining_current = list(current)
    remaining_proposed = list(proposed)
    matches = []

    current_by_id = {
        row["id"]: row for row in remaining_current if row.get("id") is not None
    }
    for proposed_row in list(remaining_proposed):
        if proposed_row.get("_force_create"):
            continue
        row_id = proposed_row.get("id")
        if row_id is None or row_id not in current_by_id:
            continue
        current_row = current_by_id[row_id]
        matches.append((current_row, proposed_row))
        remaining_current.remove(current_row)
        remaining_proposed.remove(proposed_row)

    if (
        match_single
        and len(remaining_current) == len(remaining_proposed) == 1
        and not remaining_proposed[0].get("_force_create")
    ):
        matches.append((remaining_current.pop(), remaining_proposed.pop()))

    current_by_signature = _unique_signatures(
        remaining_current,
        lambda row: tuple(row.get(field) for field in signature_fields),
    )
    proposed_by_signature = _unique_signatures(
        [row for row in remaining_proposed if not row.get("_force_create")],
        lambda row: tuple(row.get(field) for field in signature_fields),
    )
    shared_signatures = current_by_signature.keys() & proposed_by_signature.keys()
    for signature in sorted(shared_signatures, key=repr):
        current_row = current_by_signature[signature]
        proposed_row = proposed_by_signature[signature]
        matches.append((current_row, proposed_row))
        remaining_current.remove(current_row)
        remaining_proposed.remove(proposed_row)
    return matches, remaining_current, remaining_proposed


def _snapshot_sort_key(row):
    """Sort evidence rows deterministically, including ID-free model output."""
    row_id = row.get("id")
    return (
        row_id is None,
        row_id if row_id is not None else 0,
        json.dumps(_source_content(row), sort_keys=True, default=str),
    )


def _snapshot_label(row, fallback):
    return row.get("name") or row.get("id") or fallback


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
    instance.save()


def _history_delete(instance, reviewer, reason):
    instance._history_user = reviewer
    instance._change_reason = reason
    instance.delete()


def _full_clean(instance, exclude=None):
    try:
        instance.full_clean(exclude=exclude or set())
    except ValidationError as exc:
        raise ReconciliationValidationError(_validation_message(exc)) from exc


def _validation_message(exc):
    if hasattr(exc, "message_dict"):
        return "; ".join(
            f"{field}: {' '.join(messages)}"
            for field, messages in exc.message_dict.items()
        )
    return "; ".join(exc.messages)


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
