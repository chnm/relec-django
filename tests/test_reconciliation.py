from copy import deepcopy

import pytest
from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError

from census.models import ReconciliationSource, ScheduleReconciliation
from census.transcription import reconciliation as reconciliation_service
from census.transcription.contracts import load_contract
from census.transcription.reconciliation import (
    ReconciliationValidationError,
    StaleReconciliationError,
    apply_reconciliation,
    build_reconciliation_preview,
    canonical_fingerprint,
    infer_reconciliation_outcome,
    serialize_canonical,
)
from census.transcription.status import with_ai_status
from tests.factories import (
    CensusScheduleFactory,
    ClergyFactory,
    MembershipFactory,
    ReligiousBodyFactory,
    ScheduleTranscriptionFactory,
    TranscriptionJobFactory,
    TranscriptionRunFactory,
)


@pytest.fixture
def reviewer(db):
    user = User.objects.create_user(username="reconciliation-reviewer", is_staff=True)
    group, _ = Group.objects.get_or_create(name="Reviewers")
    user.groups.add(group)
    return user


def agent_candidate(**schedule_overrides):
    schedule_fields = {
        "populated_place_verbatim": None,
        "populated_place_id": None,
        "county_verbatim": None,
        "state_verbatim": None,
        "num_assistant_pastors": 1,
        "respondent": {
            "name": "Agent Respondent",
            "title": "Clerk",
            "po_address": "Agent PO",
            "date_signed": "1926-05-03",
        },
        "processing": {
            "date_received": "1926-05-04",
            "district_stamp": "Agent District",
            "denomination_code_stamp": "1-2-3",
        },
        "marginalia": [],
        "ai_notes": "Reviewed agent note",
    }
    schedule_fields.update(schedule_overrides)
    return {
        "schema_version": "relec-1926-v1",
        "schedule_fields": schedule_fields,
        "religious_bodies": [
            {
                "name": "Agent Church",
                "census_code": "A-1",
                "division": None,
                "address": "22 New Street",
                "urban_rural_code": "U",
                "membership": {
                    "male_members": 10,
                    "female_members": 15,
                    "total_members_by_sex": 25,
                    "members_under_13": 5,
                    "members_13_and_older": 20,
                    "total_members_by_age": 25,
                    "sunday_school_num_officers_teachers": 2,
                    "sunday_school_num_scholars": 12,
                    "vbs_num_officers_teachers": 1,
                    "vbs_num_scholars": 8,
                    "weekday_num_officers_teachers": 0,
                    "weekday_num_scholars": 0,
                    "parochial_num_administrators": 0,
                    "parochial_num_elementary_teachers": 0,
                    "parochial_num_secondary_teachers": 0,
                    "parochial_num_elementary_scholars": 0,
                    "parochial_num_secondary_scholars": 0,
                },
                "num_edifices": 1,
                "edifice_value": 12000,
                "edifice_debt": 1000,
                "has_pastors_residence": True,
                "residence_value": 4000,
                "residence_debt": 500,
                "expenses": 900,
                "benevolences": 100,
                "total_expenditures": 1000,
            }
        ],
        "clergy": [
            {
                "name": "Rev. Agent",
                "is_assistant": False,
                "college": "Agent College",
                "theological_seminary": None,
                "num_other_churches_served": 0,
                "serving_congregation": True,
            }
        ],
    }


def agent_source(schedule, data=None):
    contract = load_contract()
    run = TranscriptionRunFactory(
        kind="agent",
        metadata={
            "model": "test-model",
            "contract_version": contract["version"],
            "schema": contract["schema"],
        },
    )
    return ScheduleTranscriptionFactory(
        census_schedule=schedule,
        run=run,
        data=data or agent_candidate(),
    )


def canonical_schedule():
    schedule = CensusScheduleFactory(
        transcription_status="completed",
        respondent_name="Human Respondent",
    )
    body = ReligiousBodyFactory(
        census_record=schedule,
        denomination=schedule.schedule_denomination,
        name="Human Church",
        address="11 Old Street",
        latitude=38.0,
        longitude=-77.0,
        geocode_status="success",
    )
    MembershipFactory(
        census_record=schedule,
        religious_body=body,
        male_members=4,
        female_members=6,
        total_members_by_sex=10,
    )
    ClergyFactory(census_schedule=schedule, name="Rev. Human")
    return schedule


@pytest.mark.django_db
def test_canonical_fingerprint_is_deterministic():
    schedule = canonical_schedule()
    first = serialize_canonical(schedule)
    second = serialize_canonical(schedule)

    assert first == second
    assert canonical_fingerprint(first) == canonical_fingerprint(second)


@pytest.mark.django_db
def test_reviewer_can_keep_current_data_and_approve(reviewer):
    schedule = canonical_schedule()
    source = agent_source(schedule)
    before = serialize_canonical(schedule)
    preview = build_reconciliation_preview(schedule)

    event = apply_reconciliation(
        schedule_id=schedule.pk,
        reviewer=reviewer,
        outcome=ScheduleReconciliation.Outcome.RETAINED_CURRENT,
        expected_fingerprint=preview["before_fingerprint"],
        transcription_id=source.pk,
        notes="Human data matches the image.",
    )

    schedule.refresh_from_db()
    assert schedule.transcription_status == "approved"
    assert serialize_canonical(schedule) == before
    assert event.canonical_before == event.canonical_after
    assert event.reviewer == reviewer
    assert event.sources.get().disposition == ReconciliationSource.Disposition.REJECTED
    assert schedule.history.first().history_user == reviewer


@pytest.mark.django_db
def test_reviewer_can_promote_one_agent_candidate_atomically(reviewer):
    schedule = canonical_schedule()
    source = agent_source(schedule)
    preview = build_reconciliation_preview(schedule, source)
    assert infer_reconciliation_outcome(preview) == (
        ScheduleReconciliation.Outcome.PROMOTED_CANDIDATE
    )

    event = apply_reconciliation(
        schedule_id=schedule.pk,
        reviewer=reviewer,
        outcome=ScheduleReconciliation.Outcome.PROMOTED_CANDIDATE,
        expected_fingerprint=preview["before_fingerprint"],
        transcription_id=source.pk,
    )

    schedule.refresh_from_db()
    body = schedule.church_details.get()
    membership = body.membership.get()
    assert schedule.transcription_status == "approved"
    assert schedule.respondent_name == "Agent Respondent"
    assert schedule.assigned_reviewer_id is None
    assert body.name == "Agent Church"
    assert body.address == "22 New Street"
    assert body.geocode_status == "pending"
    assert membership.total_members_by_sex == 25
    assert schedule.clergy.get().name == "Rev. Agent"
    assert event.sources.get().disposition == ReconciliationSource.Disposition.ACCEPTED
    assert event.canonical_before != event.canonical_after
    assert schedule.history.first().history_user == reviewer
    assert body.history.first().history_user == reviewer


@pytest.mark.django_db
def test_promotion_preserves_geocoding_when_address_is_unchanged(reviewer):
    schedule = canonical_schedule()
    candidate = agent_candidate()
    candidate["religious_bodies"][0]["address"] = "11 Old Street"
    source = agent_source(schedule, candidate)
    preview = build_reconciliation_preview(schedule, source)

    apply_reconciliation(
        schedule_id=schedule.pk,
        reviewer=reviewer,
        outcome=ScheduleReconciliation.Outcome.PROMOTED_CANDIDATE,
        expected_fingerprint=preview["before_fingerprint"],
        transcription_id=source.pk,
    )

    body = schedule.church_details.get()
    assert body.name == "Agent Church"
    assert body.latitude == 38.0
    assert body.longitude == -77.0
    assert body.geocode_status == "success"
    assert preview["operations"]["geocoding_resets"] == 0


@pytest.mark.django_db
def test_promotion_ignores_operational_fields_in_human_snapshot(reviewer):
    schedule = canonical_schedule()
    schedule.assigned_reviewer = reviewer
    schedule.save()
    snapshot = serialize_canonical(schedule)
    snapshot["schedule_fields"].update(
        {
            "respondent_name": "Snapshot Respondent",
            "schedule_title": "Attempted replacement",
            "schedule_denomination_id": None,
            "assigned_reviewer_id": None,
            "resource_id": -1,
        }
    )
    source = ScheduleTranscriptionFactory(
        census_schedule=schedule,
        run=TranscriptionRunFactory(kind="human_snapshot"),
        data=snapshot,
    )
    preview = build_reconciliation_preview(schedule, source)

    apply_reconciliation(
        schedule_id=schedule.pk,
        reviewer=reviewer,
        outcome=ScheduleReconciliation.Outcome.PROMOTED_CANDIDATE,
        expected_fingerprint=preview["before_fingerprint"],
        transcription_id=source.pk,
    )

    schedule.refresh_from_db()
    assert schedule.respondent_name == "Snapshot Respondent"
    assert schedule.schedule_title != "Attempted replacement"
    assert schedule.resource_id != -1
    assert schedule.schedule_denomination_id is not None
    assert schedule.assigned_reviewer == reviewer


@pytest.mark.django_db
def test_reviewer_can_mix_current_and_candidate_fields_with_provenance(reviewer):
    schedule = canonical_schedule()
    body = schedule.church_details.get()
    membership = body.membership.get()
    current_clergy = schedule.clergy.get()
    source = agent_source(
        schedule,
        agent_candidate(
            marginalia=[
                {
                    "page_location": "top margin",
                    "marginalia_transcription": "Copy",
                }
            ],
            ai_notes="Candidate-only review context",
        ),
    )
    decisions = {
        "schedule.respondent_name": "current",
        f"body.{body.pk}.name": "current",
        f"membership.{membership.pk}.male_members": "current",
        f"entity.clergy.{current_clergy.pk}": "current",
        "entity.clergy.new.0": "current",
    }
    preview = build_reconciliation_preview(
        schedule,
        source,
        decisions=decisions,
        mixed=True,
    )
    assert "schedule.marginalia" not in preview["decisions"]
    assert "schedule.ai_notes" not in preview["decisions"]
    context_sections = {
        section["title"]: section for section in preview["review_sections"]
    }
    assert context_sections["Marginalia"]["decision_scope"] == "automatic"
    assert context_sections["Agent notes"]["decision_scope"] == "automatic"
    assert infer_reconciliation_outcome(preview) == (
        ScheduleReconciliation.Outcome.MIXED
    )

    event = apply_reconciliation(
        schedule_id=schedule.pk,
        reviewer=reviewer,
        outcome=ScheduleReconciliation.Outcome.MIXED,
        expected_fingerprint=preview["before_fingerprint"],
        transcription_id=source.pk,
        decisions=decisions,
    )

    schedule.refresh_from_db()
    body.refresh_from_db()
    membership.refresh_from_db()
    assert schedule.respondent_name == "Human Respondent"
    assert schedule.respondent_title == "Clerk"
    assert schedule.marginalia == [
        {
            "page_location": "top margin",
            "marginalia_transcription": "Copy",
        }
    ]
    assert schedule.ai_notes == "Candidate-only review context"
    assert body.name == "Human Church"
    assert body.address == "22 New Street"
    assert body.geocode_status == "pending"
    assert membership.male_members == 4
    assert membership.female_members == 15
    assert list(schedule.clergy.values_list("name", flat=True)) == ["Rev. Human"]
    assert event.outcome == ScheduleReconciliation.Outcome.MIXED
    assert event.sources.get().disposition == (
        ReconciliationSource.Disposition.INCORPORATED
    )
    assert event.decisions["field_source_decisions"][
        "schedule.respondent_name"
    ] == "current"


@pytest.mark.django_db
def test_reviewer_can_apply_typed_inline_edits_with_provenance(reviewer):
    schedule = canonical_schedule()
    body = schedule.church_details.get()
    source = agent_source(schedule)
    decisions = {
        "schedule.respondent_name": {
            "source": "edited",
            "base": "candidate",
            "value": "Reviewer Corrected",
        },
        f"body.{body.pk}.expenses": {
            "source": "edited",
            "base": "current",
            "value": "1234.50",
        },
    }

    preview = build_reconciliation_preview(
        schedule,
        source,
        decisions=decisions,
        mixed=True,
    )
    assert preview["proposed"]["schedule_fields"]["respondent_name"] == (
        "Reviewer Corrected"
    )
    assert preview["proposed"]["religious_bodies"][0]["expenses"] == (
        "1234.50"
    )
    assert preview["decisions"]["schedule.respondent_name"] == decisions[
        "schedule.respondent_name"
    ]

    event = apply_reconciliation(
        schedule_id=schedule.pk,
        reviewer=reviewer,
        outcome=ScheduleReconciliation.Outcome.MIXED,
        expected_fingerprint=preview["before_fingerprint"],
        transcription_id=source.pk,
        decisions=decisions,
    )

    schedule.refresh_from_db()
    body.refresh_from_db()
    assert schedule.respondent_name == "Reviewer Corrected"
    assert str(body.expenses) == "1234.50"
    assert event.decisions["reviewer_overrides"] == [
        {
            "field": "schedule.respondent_name",
            "source": "edited",
            "base": "candidate",
            "value": "Reviewer Corrected",
        },
        {
            "field": f"body.{body.pk}.expenses",
            "source": "edited",
            "base": "current",
            "value": "1234.50",
        },
    ]


@pytest.mark.django_db
def test_inline_edit_rejects_invalid_typed_values(reviewer):
    schedule = canonical_schedule()
    source = agent_source(schedule)

    with pytest.raises(ReconciliationValidationError, match="whole number"):
        build_reconciliation_preview(
            schedule,
            source,
            decisions={
                "schedule.num_assistant_pastors": {
                    "source": "edited",
                    "base": "candidate",
                    "value": "several",
                }
            },
            mixed=True,
        )


@pytest.mark.django_db
def test_mixed_review_requires_explicit_choices_for_unmatched_repeated_bodies(
    reviewer,
):
    schedule = canonical_schedule()
    first_current = schedule.church_details.get()
    second_current = ReligiousBodyFactory(
        census_record=schedule,
        denomination=schedule.schedule_denomination,
        name="Second Human Church",
        address="12 Old Street",
        census_code="H-2",
    )
    candidate = agent_candidate()
    second_candidate = deepcopy(candidate["religious_bodies"][0])
    second_candidate.update(
        {
            "name": "Second Agent Church",
            "address": "23 New Street",
            "census_code": "A-2",
        }
    )
    candidate["religious_bodies"].append(second_candidate)
    source = agent_source(schedule, candidate)
    decisions = {
        f"entity.body.{first_current.pk}": "current",
        f"entity.body.{second_current.pk}": "candidate",
        "entity.body.new.0": "candidate",
        "entity.body.new.1": "current",
        f"entity.clergy.{schedule.clergy.get().pk}": "current",
        "entity.clergy.new.0": "current",
    }

    preview = build_reconciliation_preview(
        schedule,
        source,
        decisions=decisions,
        mixed=True,
    )
    assert {body["name"] for body in preview["proposed"]["religious_bodies"]} == {
        "Human Church",
        "Agent Church",
    }
    assert preview["operations"]["religious_bodies"] == {
        "updated": 0,
        "added": 1,
        "removed": 1,
    }

    apply_reconciliation(
        schedule_id=schedule.pk,
        reviewer=reviewer,
        outcome=ScheduleReconciliation.Outcome.MIXED,
        expected_fingerprint=preview["before_fingerprint"],
        transcription_id=source.pk,
        decisions=decisions,
    )

    assert set(schedule.church_details.values_list("name", flat=True)) == {
        "Human Church",
        "Agent Church",
    }


@pytest.mark.django_db
def test_stale_preview_cannot_overwrite_newer_canonical_edits(reviewer):
    schedule = canonical_schedule()
    source = agent_source(schedule)
    preview = build_reconciliation_preview(schedule, source)
    schedule.respondent_name = "Edited after preview"
    schedule.save()

    with pytest.raises(StaleReconciliationError):
        apply_reconciliation(
            schedule_id=schedule.pk,
            reviewer=reviewer,
            outcome=ScheduleReconciliation.Outcome.PROMOTED_CANDIDATE,
            expected_fingerprint=preview["before_fingerprint"],
            transcription_id=source.pk,
        )

    schedule.refresh_from_db()
    assert schedule.transcription_status == "completed"
    assert schedule.respondent_name == "Edited after preview"
    assert not ScheduleReconciliation.objects.exists()


@pytest.mark.django_db
def test_invalid_candidate_fails_without_canonical_writes(reviewer):
    schedule = canonical_schedule()
    invalid = agent_candidate()
    invalid["religious_bodies"][0]["membership"]["male_members"] = -1
    source = agent_source(schedule, invalid)
    before = serialize_canonical(schedule)

    with pytest.raises(ReconciliationValidationError):
        build_reconciliation_preview(schedule, source)

    schedule.refresh_from_db()
    assert serialize_canonical(schedule) == before
    assert schedule.transcription_status == "completed"


@pytest.mark.django_db
def test_failed_write_rolls_back_the_complete_canonical_graph(reviewer, monkeypatch):
    schedule = canonical_schedule()
    source = agent_source(schedule)
    preview = build_reconciliation_preview(schedule, source)
    before = serialize_canonical(schedule)
    original_history_save = reconciliation_service._history_save
    calls = 0

    def fail_after_first_write(instance, acting_reviewer, reason):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("simulated mid-transaction failure")
        return original_history_save(instance, acting_reviewer, reason)

    monkeypatch.setattr(
        reconciliation_service,
        "_history_save",
        fail_after_first_write,
    )

    with pytest.raises(RuntimeError, match="mid-transaction"):
        apply_reconciliation(
            schedule_id=schedule.pk,
            reviewer=reviewer,
            outcome=ScheduleReconciliation.Outcome.PROMOTED_CANDIDATE,
            expected_fingerprint=preview["before_fingerprint"],
            transcription_id=source.pk,
        )

    schedule.refresh_from_db()
    assert serialize_canonical(schedule) == before
    assert schedule.transcription_status == "completed"
    assert not ScheduleReconciliation.objects.exists()


@pytest.mark.django_db
def test_reconciliation_evidence_and_dispositions_are_immutable(reviewer):
    schedule = canonical_schedule()
    source = agent_source(schedule)
    preview = build_reconciliation_preview(schedule)
    event = apply_reconciliation(
        schedule_id=schedule.pk,
        reviewer=reviewer,
        outcome=ScheduleReconciliation.Outcome.RETAINED_CURRENT,
        expected_fingerprint=preview["before_fingerprint"],
        transcription_id=source.pk,
    )

    event.notes = "rewrite history"
    with pytest.raises(ValidationError):
        event.save()
    with pytest.raises(ValidationError):
        event.sources.get().delete()


@pytest.mark.django_db
def test_reviewed_agent_candidate_leaves_pending_ai_queue(reviewer):
    schedule = canonical_schedule()
    source = agent_source(schedule)
    TranscriptionJobFactory(
        census_schedule=schedule,
        run=source.run,
        state="succeeded",
    )
    preview = build_reconciliation_preview(schedule)
    apply_reconciliation(
        schedule_id=schedule.pk,
        reviewer=reviewer,
        outcome=ScheduleReconciliation.Outcome.RETAINED_CURRENT,
        expected_fingerprint=preview["before_fingerprint"],
        transcription_id=source.pk,
    )

    annotated = with_ai_status(type(schedule).objects.all()).get(pk=schedule.pk)
    assert annotated._ai_status == "reviewed"

    newer = agent_source(schedule, deepcopy(agent_candidate(ai_notes="newer")))
    TranscriptionJobFactory(
        census_schedule=schedule,
        run=newer.run,
        state="succeeded",
    )
    annotated = with_ai_status(type(schedule).objects.all()).get(pk=schedule.pk)
    assert annotated._ai_status == "transcribed"
