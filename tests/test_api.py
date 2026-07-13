import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from census.models import Denomination, ReligiousBody
from tests.factories import (
    CensusScheduleFactory,
    ClergyFactory,
    DenominationFactory,
    MembershipFactory,
    ReligiousBodyFactory,
)


@pytest.mark.django_db
def test_religious_body_list_uses_bounded_queries(client):
    for _ in range(12):
        schedule = CensusScheduleFactory()
        body = ReligiousBodyFactory(census_record=schedule)
        MembershipFactory(census_record=schedule, religious_body=body)
        ClergyFactory(census_schedule=schedule)

    with CaptureQueriesContext(connection) as queries:
        response = client.get(reverse("religiousbody-list"), {"page_size": 100})

    assert response.status_code == 200
    assert len(queries) <= 6


@pytest.mark.django_db
def test_religious_body_list_preserves_nested_response(client):
    ai_transcription = {
        "schedule_fields": {"schedule_id": "AI-123"},
        "religious_bodies": [{"name": "AI Church"}],
        "clergy": [],
    }
    human_transcription = {
        "schedule_fields": {"schedule_id": "HUMAN-123"},
        "religious_bodies": [{"name": "Human Church"}],
        "clergy": [],
    }
    schedule = CensusScheduleFactory(
        ai_transcription=ai_transcription,
        human_transcription=human_transcription,
        ai_notes="The total is difficult to read.",
    )
    body = ReligiousBodyFactory(census_record=schedule)
    MembershipFactory(
        census_record=schedule,
        religious_body=body,
        total_members_by_sex=125,
    )
    ClergyFactory(census_schedule=schedule, name="Rev. Example")

    response = client.get(reverse("religiousbody-list"))

    result = response.json()["results"][0]
    assert result["membership_details"]["total_members"] == 125
    assert result["pastors"][0]["name"] == "Rev. Example"
    assert result["transcription"] == {
        "status": schedule.transcription_status,
        "ai": ai_transcription,
        "human": human_transcription,
        "ai_notes": "The total is difficult to read.",
    }
    assert "transcription_status" not in result
    assert "ai_transcription" not in result
    assert "human_transcription" not in result


@pytest.mark.django_db
def test_religious_body_transcriptions_are_null_when_unavailable(client):
    ReligiousBodyFactory(
        census_record=CensusScheduleFactory(
            ai_transcription=None,
            human_transcription=None,
        )
    )

    response = client.get(reverse("religiousbody-list"))

    result = response.json()["results"][0]
    assert result["transcription"]["ai"] is None
    assert result["transcription"]["human"] is None


@pytest.mark.django_db
def test_map_view_uses_smaller_payload_and_fewer_queries(client):
    schedule = CensusScheduleFactory()
    body = ReligiousBodyFactory(census_record=schedule)
    MembershipFactory(census_record=schedule, religious_body=body)
    ClergyFactory(census_schedule=schedule)

    with CaptureQueriesContext(connection) as queries:
        response = client.get(
            reverse("religiousbody-list"),
            {"page_size": 5000, "view": "map"},
        )

    result = response.json()["results"][0]
    assert response.status_code == 200
    assert len(queries) <= 5
    assert "location_details" in result
    assert "membership_details" in result
    assert "pastors" not in result
    assert result["transcription"] == {"status": schedule.transcription_status}


@pytest.mark.django_db
def test_family_filter_combines_body_and_schedule_denominations(client):
    family = "Shared Family"
    other = DenominationFactory(family_relec="Other Family")
    direct_match = ReligiousBodyFactory(
        denomination=DenominationFactory(family_relec=family)
    )
    schedule_match = ReligiousBodyFactory(
        denomination=other,
        census_record=CensusScheduleFactory(
            schedule_denomination=DenominationFactory(family_relec=family)
        ),
    )
    ReligiousBodyFactory(denomination=other)

    response = client.get(
        reverse("religiousbody-list"),
        {"family_relec": family},
    )

    assert response.status_code == 200
    assert {result["id"] for result in response.json()["results"]} == {
        direct_match.id,
        schedule_match.id,
    }


@pytest.mark.django_db
def test_denomination_by_family_uses_relec_family(client):
    matching = DenominationFactory(family_relec="Baptist")
    other = DenominationFactory(family_relec="Methodist")
    ReligiousBodyFactory(denomination=matching)
    ReligiousBodyFactory(denomination=other)

    response = client.get(
        reverse("denomination-by-family"),
        {"family_relec": "Baptist"},
    )

    assert response.status_code == 200
    assert [result["id"] for result in response.json()] == [matching.id]


@pytest.mark.django_db
def test_denomination_families_returns_counted_objects(client):
    denomination = DenominationFactory(
        family_census="Baptist bodies",
        family_relec="Baptist",
    )
    ReligiousBodyFactory(denomination=denomination)

    response = client.get(reverse("denomination-families"))

    assert response.status_code == 200
    data = response.json()
    assert data["census_families"] == [{"name": "Baptist bodies", "count": 1}]
    assert data["relec_families"] == [{"name": "Baptist", "count": 1}]


@pytest.mark.django_db
def test_api_root_uses_live_totals_and_documents_current_filters(client):
    denomination = DenominationFactory()
    ReligiousBodyFactory(denomination=denomination)

    response = client.get(reverse("census-api-root"))

    assert response.status_code == 200
    data = response.json()
    assert data["info"]["total_denominations"] == Denomination.objects.count()
    assert data["info"]["total_congregations"] == ReligiousBody.objects.count()
    assert "family_relec=Adventist" in data["endpoints"]["denominations"]["by_family"]
    filters = data["endpoints"]["religious_bodies"]["filters"]
    assert "has_location (boolean)" in filters
    assert "page (integer, default page size 100)" in filters
    response_notes = data["endpoints"]["religious_bodies"]["response_notes"]
    assert "transcription" in response_notes
    assert "ai_transcription" not in response_notes
    assert "human_transcription" not in response_notes


@pytest.mark.django_db
def test_api_documentation_describes_current_contract(client):
    response = client.get(reverse("api_documentation"))

    assert response.status_code == 200
    content = response.content.decode()
    assert "denominations/by_family/?family_relec=Baptist" in content
    assert "denominations/by_family/?family_census=" not in content
    assert '<span class="param-name">has_location</span>' in content
    assert '<span class="param-name">ordering</span>' in content
    assert '"pastors": [{' in content
    assert '"transcription": {' in content
