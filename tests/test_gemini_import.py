import json

import pytest
from django.core.management import call_command

from census.models import ScheduleTranscription

from .factories import CensusScheduleFactory


def _result():
    return {
        "identification": {"qb_division": "Cumberland Valley Conf.", "qc_church_name": "Himyar", "denomination_code": "0-2", "date_received_stamp": ""},
        "location": {"qd_city_town_village": "Himyar", "qe_county": "Knox", "qf_state": "Ky.", "street_address": "NA", "urban_rural": "R"},
        "edifice_property": {"q7_number_of_edifices": "0", "q8_value_of_edifice_usd": "$1,200.75", "q9_debt_on_edifice_usd": "NA", "q10_owns_parsonage": "FALSE", "q11_value_of_parsonage_usd": "NA", "q12_debt_on_parsonage_usd": ""},
        "membership": {"q1_male_members": "15", "q2_female_members": "18", "q3_total_members": "33", "q4_members_under_13": "-2", "q5_members_13_and_over": "33", "q6_total_members_by_age": "33"},
        "expenditures": {"q13_current_expenses_usd": "0", "q14_benevolences_missions_usd": "0", "q15_total_expenditures_usd": "0"},
        "sunday_school": {"q16_officers_teachers": "0", "q17_scholars": "0"},
        "vacation_bible_school": {"q18_officers_teachers": "NA", "q19_scholars": "NA"},
        "weekday_religious_school": {"q20_officers_teachers": "NA", "q21_scholars": "NA"},
        "parochial_school": {"q22_administrators": "NA", "q23a_elementary_teachers": "NA", "q23b_secondary_teachers": "NA", "q24a_elementary_scholars": "NA", "q24b_secondary_scholars": "NA"},
        "pastor": {"q25_name": "Rev. F. E. Banks", "q26_num_assistant_pastors": "0", "q27_num_other_churches_served": "2", "q28_college": "NO", "q29_theological_seminary": "Aurora College"},
        "assistant_pastors": [{"name": "NA", "q30_college": "NO", "q31_theological_seminary": "NA"}],
        "certification": {},
        "bureau_marginalia": "0-0-0",
        "confidence": {"notes": "Clear.", "fields_flagged_low_confidence": ["membership.q4_members_under_13"]},
    }


@pytest.mark.django_db
def test_import_maps_gemini_record_and_is_idempotent(tmp_path):
    schedule = CensusScheduleFactory()
    target = tmp_path / "0-0-0_advent-christian-church"
    (target / "records").mkdir(parents=True)
    (target / "generation.json").write_text(
        json.dumps({"model": "gemini-3.5-flash", "transcription_policy": "2026-09-20"})
    )
    record = {
        "record_id": 42,
        "api_metadata": {"schedule_id": schedule.schedule_id, "urls": {"self": f"http://religiousecologies.org/census/record/{schedule.resource_id}/"}},
        "extraction": {"result": _result(), "field_locations": {"membership.q1_male_members": [320, 410, 348, 480]}},
        "validation": {"passed": True, "issues": []},
    }
    (target / "records" / f"{schedule.pk}.json").write_text(json.dumps(record))
    (target / "records" / "999999.json").write_text(json.dumps({**record, "record_id": 43, "api_metadata": {"schedule_id": "x", "urls": {"self": "/census/record/999999/"}}}))

    call_command("import_gemini_transcriptions", str(target))
    call_command("import_gemini_transcriptions", str(target))

    transcription = ScheduleTranscription.objects.get()
    assert transcription.run.key == "gemini-3-5-flash-2026-09-20-0-0-0"
    assert transcription.run.kind == "agent"
    data = transcription.data
    body = data["religious_bodies"][0]
    assert body["urban_rural_code"] == "R"
    assert body["address"] is None
    assert body["edifice_value"] == 1200
    assert body["residence_debt"] is None
    assert body["has_pastors_residence"] is False
    assert body["membership"]["male_members"] == 15
    assert body["membership"]["members_under_13"] is None
    assert data["clergy"] == [
        {"name": "Rev. F. E. Banks", "is_assistant": False, "college": None, "theological_seminary": "Aurora College", "num_other_churches_served": 2, "serving_congregation": None}
    ]
    fields = data["schedule_fields"]
    assert fields["marginalia"][0]["marginalia_transcription"] == "0-0-0"
    assert "negative" in fields["ai_notes"] and "Flagged: membership.q4" in fields["ai_notes"]
    assert data["_field_locations"]["membership.q1_male_members"] == [320, 410, 348, 480]

