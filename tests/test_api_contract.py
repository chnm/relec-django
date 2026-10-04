from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from tests.factories import (
    CensusScheduleFactory,
    ClergyFactory,
    CountyFactory,
    DenominationFactory,
    MembershipFactory,
    PopulatedPlaceFactory,
    ReligiousBodyFactory,
    ScheduleTranscriptionFactory,
    StateFactory,
    TranscriptionRunFactory,
)


@pytest.mark.django_db
def test_religious_body_detail_returns_complete_contract(client):
    state = StateFactory(code="CT", name="Connecticut")
    county = CountyFactory(state=state, name="Hartford", ahcb_id="ct003")
    place = PopulatedPlaceFactory(
        county=county,
        name="Hartford",
        place_id=123,
        lat=41.7658,
        lon=-72.6734,
    )
    denomination = DenominationFactory(
        denomination_id="denom-7",
        name="Test Baptist Convention",
        family_census="Baptist bodies",
        family_relec="Baptist",
    )
    ai = {
        "schedule_fields": {"schedule_id": "CT-7"},
        "ai_notes": "Verified against the image.",
    }
    human = {"schedule_fields": {"schedule_id": "CT-7-H"}}
    schedule = CensusScheduleFactory(
        schedule_id="CT-7",
        resource_id=7007,
        county=county,
        populated_place=place,
        schedule_denomination=denomination,
        transcription_status="approved",
        num_assistant_pastors=1,
        respondent_name="Jane Doe",
        respondent_title="Clerk",
        respondent_po_address="Hartford, CT",
        respondent_date_signed=date(1926, 5, 1),
        date_received=date(1926, 5, 10),
        district_stamp="7",
        denomination_code_stamp="B-12",
        marginalia=[{"page_location": "top", "marginalia_transcription": "Copy"}],
    )
    ScheduleTranscriptionFactory(
        census_schedule=schedule,
        run=TranscriptionRunFactory(
            key="human-snapshot",
            kind="human_snapshot",
        ),
        data=human,
    )
    ScheduleTranscriptionFactory(
        census_schedule=schedule,
        run=TranscriptionRunFactory(
            key="sonnet-high-2026-08-26",
            kind="agent",
        ),
        data=ai,
    )
    body = ReligiousBodyFactory(
        census_record=schedule,
        denomination=denomination,
        name="First Test Baptist Church",
        census_code="B-12",
        division="Northern",
        address="1 Main Street",
        urban_rural_code="Urban",
        num_edifices=2,
        has_pastors_residence=True,
        expenses=Decimal("1200.50"),
        benevolences=Decimal("300.25"),
        total_expenditures=Decimal("1500.75"),
        edifice_value=Decimal("25000.00"),
        edifice_debt=Decimal("5000.00"),
        residence_value=Decimal("8000.00"),
        residence_debt=Decimal("1000.00"),
    )
    MembershipFactory(
        census_record=schedule,
        religious_body=body,
        male_members=40,
        female_members=60,
        total_members_by_sex=100,
        members_under_13=20,
        members_13_and_older=80,
        total_members_by_age=100,
        sunday_school_num_officers_teachers=5,
        sunday_school_num_scholars=30,
        vbs_num_officers_teachers=4,
        vbs_num_scholars=25,
        weekday_num_officers_teachers=3,
        weekday_num_scholars=20,
        parochial_num_administrators=1,
        parochial_num_elementary_teachers=6,
        parochial_num_secondary_teachers=2,
        parochial_num_elementary_scholars=50,
        parochial_num_secondary_scholars=15,
    )
    ClergyFactory(
        census_schedule=schedule,
        name="Rev. Example",
        college="Example College",
        theological_seminary="Example Seminary",
        num_other_churches_served=1,
        serving_congregation=True,
    )

    response = client.get(reverse("religiousbody-detail", args=[body.pk]))

    assert response.status_code == 200
    assert response.json() == {
        "id": body.pk,
        "name": "First Test Baptist Church",
        "census_code": "B-12",
        "division": "Northern",
        "schedule_id": "CT-7",
        "transcriptions": [
            {
                "key": "human-snapshot",
                "kind": "human_snapshot",
                "data": human,
            },
            {
                "key": "sonnet-high-2026-08-26",
                "kind": "agent",
                "data": ai,
            },
        ],
        "has_location": True,
        "location_details": {
            "lat": 41.7658,
            "lon": -72.6734,
            "city_name": "Hartford",
            "map_name": "Hartford",
            "place_id": 123,
            "county_ahcb": "ct003",
            "county_name": "Hartford",
            "state_name": "CT",
            "address": "1 Main Street",
            "urban_rural_code": "Urban",
        },
        "denomination_details": {
            "id": denomination.pk,
            "denomination_id": "denom-7",
            "name": "Test Baptist Convention",
            "family_census": "Baptist bodies",
            "family_relec": "Baptist",
        },
        "membership_details": {
            "male_members": 40,
            "female_members": 60,
            "total_members": 100,
            "members_under_13": 20,
            "members_13_and_older": 80,
            "total_by_age": 100,
            "sunday_school_num_officers_teachers": 5,
            "sunday_school_num_scholars": 30,
            "vbs_num_officers_teachers": 4,
            "vbs_num_scholars": 25,
            "weekday_num_officers_teachers": 3,
            "weekday_num_scholars": 20,
            "parochial_num_administrators": 1,
            "parochial_num_elementary_teachers": 6,
            "parochial_num_secondary_teachers": 2,
            "parochial_num_elementary_scholars": 50,
            "parochial_num_secondary_scholars": 15,
        },
        "num_edifices": 2,
        "has_pastors_residence": True,
        "finances": {
            "expenditures": 1200.5,
            "benevolences": 300.25,
            "total_expenditures": 1500.75,
            "edifice_value": 25000.0,
            "edifice_debt": 5000.0,
            "residence_value": 8000.0,
            "residence_debt": 1000.0,
        },
        "pastors": [
            {
                "name": "Rev. Example",
                "is_assistant": False,
                "college": "Example College",
                "theological_seminary": "Example Seminary",
                "num_other_churches_served": 1,
                "serving_congregation": True,
            }
        ],
        "num_assistant_pastors": 1,
        "respondent": {
            "name": "Jane Doe",
            "title": "Clerk",
            "po_address": "Hartford, CT",
            "date_signed": "1926-05-01",
        },
        "processing": {
            "date_received": "1926-05-10",
            "district_stamp": "7",
            "denomination_code_stamp": "B-12",
        },
        "marginalia": [{"page_location": "top", "marginalia_transcription": "Copy"}],
        "urls": {
            "self": "http://testserver/census/record/7007/",
            "image": None,
            "family_census": "http://testserver/census/browser/?family=Baptist bodies",
            "family_relec": (
                "http://testserver/census/browser/?family=Baptist"
                f"&denomination={denomination.pk}"
            ),
        },
    }


@pytest.mark.django_db
def test_religious_body_filters_return_only_matching_records(client):
    state = StateFactory(code="VA", name="Virginia")
    county = CountyFactory(state=state, name="Fairfax")
    in_bounds = PopulatedPlaceFactory(
        county=county,
        name="Falls Church",
        place_id=10,
        lat=38.88,
        lon=-77.17,
    )
    out_bounds = PopulatedPlaceFactory(
        county=county,
        name="Remote City",
        place_id=11,
        lat=45.0,
        lon=-90.0,
    )
    baptist = DenominationFactory(
        name="Baptist Match",
        family_census="Baptist bodies",
        family_relec="Baptist",
    )
    methodist = DenominationFactory(
        name="Methodist Decoy",
        family_census="Methodist bodies",
        family_relec="Methodist",
    )
    target = ReligiousBodyFactory(
        census_record=CensusScheduleFactory(
            county=county,
            populated_place=in_bounds,
            schedule_denomination=baptist,
            transcription_status="approved",
        ),
        denomination=baptist,
        name="Alpha Target Church",
        address="123 Match Street",
        census_code="MATCH-1",
        urban_rural_code="Urban",
    )
    decoy = ReligiousBodyFactory(
        census_record=CensusScheduleFactory(
            county=county,
            populated_place=out_bounds,
            schedule_denomination=methodist,
            transcription_status="needs_review",
        ),
        denomination=methodist,
        name="Zulu Decoy Church",
        address="999 Other Avenue",
        census_code="OTHER-1",
        urban_rural_code="Rural",
    )
    no_location = ReligiousBodyFactory(
        census_record=CensusScheduleFactory(
            county=county,
            populated_place=None,
            schedule_denomination=methodist,
        ),
        denomination=methodist,
        name="No Location Church",
    )

    cases = [
        ({"denomination": baptist.pk}, {target.pk}),
        ({"family_census": "Baptist bodies"}, {target.pk}),
        ({"family_relec": "Baptist"}, {target.pk}),
        ({"transcription_status": "approved"}, {target.pk}),
        ({"exclude_families": "Methodist bodies"}, {target.pk}),
        ({"urban_rural": "urban"}, {target.pk}),
        ({"urban_rural": "rural"}, {decoy.pk}),
        ({"bounds": "38,-78,40,-75"}, {target.pk}),
        ({"has_location": "false"}, {no_location.pk}),
        ({"search": "Match Street"}, {target.pk}),
        ({"search": "MATCH-1"}, {target.pk}),
    ]

    for params, expected_ids in cases:
        response = client.get(reverse("religiousbody-list"), params)
        assert response.status_code == 200
        assert {item["id"] for item in response.json()["results"]} == expected_ids


@pytest.mark.django_db
def test_religious_body_pagination_ordering_and_map_contract(client):
    zulu = ReligiousBodyFactory(name="Zulu Church")
    alpha = ReligiousBodyFactory(name="Alpha Church")
    ReligiousBodyFactory(name="Middle Church")

    first_page = client.get(
        reverse("religiousbody-list"),
        {"ordering": "name", "page_size": 2},
    ).json()
    second_page = client.get(
        reverse("religiousbody-list"),
        {"ordering": "name", "page_size": 2, "page": 2},
    ).json()

    assert first_page["count"] == 3
    assert [item["name"] for item in first_page["results"]] == [
        "Alpha Church",
        "Middle Church",
    ]
    assert [item["name"] for item in second_page["results"]] == ["Zulu Church"]

    map_result = client.get(
        reverse("religiousbody-detail", args=[alpha.pk]),
        {"view": "map"},
    ).json()
    assert set(map_result) == {
        "id",
        "name",
        "census_code",
        "division",
        "schedule_id",
        "has_location",
        "location_details",
        "denomination_details",
        "membership_details",
        "num_edifices",
        "has_pastors_residence",
        "finances",
        "urls",
    }
    assert zulu.pk != alpha.pk


@pytest.mark.django_db
def test_denomination_list_detail_filter_search_and_pagination(client):
    baptist = DenominationFactory(
        denomination_id="B1",
        name="Alpha Baptist",
        family_census="Baptist bodies",
        family_relec="Baptist",
    )
    DenominationFactory(
        denomination_id="M1",
        name="Zulu Methodist",
        family_census="Methodist bodies",
        family_relec="Methodist",
    )

    filtered = client.get(
        reverse("denomination-list"),
        {"family_relec": "Baptist"},
    ).json()
    searched = client.get(
        reverse("denomination-list"),
        {"search": "Alpha"},
    ).json()
    detail = client.get(reverse("denomination-detail", args=[baptist.pk]))

    assert filtered["count"] == 1
    assert filtered["results"][0]["id"] == baptist.pk
    assert searched["count"] == 1
    assert detail.status_code == 200
    assert detail.json() == {
        "id": baptist.pk,
        "denomination_id": "B1",
        "name": "Alpha Baptist",
        "family_census": "Baptist bodies",
        "family_relec": "Baptist",
    }
