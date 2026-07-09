import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

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
    schedule = CensusScheduleFactory()
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
