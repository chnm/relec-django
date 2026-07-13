from decimal import Decimal

import pytest
from django.urls import reverse

from tests.factories import (
    CensusScheduleFactory,
    CountyFactory,
    DenominationFactory,
    PopulatedPlaceFactory,
    ReligiousBodyFactory,
    StateFactory,
)


@pytest.mark.django_db
def test_census_browser_filters_include_only_matching_rows(client):
    state = StateFactory(code="VA", name="Virginia")
    county = CountyFactory(state=state, name="Fairfax")
    place = PopulatedPlaceFactory(county=county, name="Falls Church")
    baptist = DenominationFactory(
        name="Browser Baptist",
        family_census="Baptist bodies",
        family_relec="Baptist",
    )
    methodist = DenominationFactory(
        name="Browser Methodist",
        family_census="Methodist bodies",
        family_relec="Methodist",
    )
    target = CensusScheduleFactory(
        schedule_title="Target Schedule",
        county=county,
        populated_place=place,
        schedule_denomination=baptist,
    )
    ReligiousBodyFactory(
        census_record=target,
        denomination=baptist,
        name="Target Congregation",
        urban_rural_code="Urban",
    )
    decoy = CensusScheduleFactory(
        schedule_title="Decoy Schedule",
        county=county,
        populated_place=place,
        schedule_denomination=methodist,
    )
    ReligiousBodyFactory(
        census_record=decoy,
        denomination=methodist,
        name="Decoy Congregation",
        urban_rural_code="Rural",
    )

    cases = [
        ({"search": "Target Congregation"}, target),
        ({"denomination": baptist.pk}, target),
        ({"family": "Baptist"}, target),
        ({"family_census": "Baptist bodies"}, target),
        ({"location": "VA"}, None),
        ({"county": "Fairfax"}, None),
        ({"place": "Falls Church"}, None),
        ({"urban_rural": "urban"}, target),
        ({"urban_rural": "rural"}, decoy),
    ]

    for params, sole_match in cases:
        response = client.get(reverse("census_browser"), params)
        assert response.status_code == 200
        records = list(response.context["page_obj"].object_list)
        if sole_match:
            assert [record.pk for record in records] == [sole_match.pk]
            content = response.content.decode()
            assert sole_match.schedule_title in content
            other = decoy if sole_match == target else target
            assert other.schedule_title not in content
        else:
            assert {record.pk for record in records} == {target.pk, decoy.pk}


@pytest.mark.django_db
def test_census_browser_membership_filter_and_empty_state(client):
    from tests.factories import MembershipFactory

    with_membership = CensusScheduleFactory(schedule_title="Has Membership")
    body = ReligiousBodyFactory(census_record=with_membership)
    MembershipFactory(census_record=with_membership, religious_body=body)
    without_membership = CensusScheduleFactory(schedule_title="No Membership")
    ReligiousBodyFactory(census_record=without_membership)

    yes_response = client.get(reverse("census_browser"), {"has_membership": "yes"})
    no_response = client.get(reverse("census_browser"), {"has_membership": "no"})
    empty_response = client.get(reverse("census_browser"), {"search": "impossible"})

    assert [record.pk for record in yes_response.context["page_obj"]] == [
        with_membership.pk
    ]
    assert [record.pk for record in no_response.context["page_obj"]] == [
        without_membership.pk
    ]
    assert "No records found" in empty_response.content.decode()


@pytest.fixture
def staff_user(django_user_model):
    return django_user_model.objects.create_user(
        username="analytics-reviewer",
        password="local-test-password",
        is_staff=True,
    )


@pytest.mark.django_db
def test_analytics_results_require_authorized_user(client):
    response = client.get(reverse("analytics:run_query"))

    assert response.status_code == 302
    assert response.url.startswith("/accounts/login/")


@pytest.mark.django_db
def test_analytics_table_filters_and_renders_correct_cells(client, staff_user):
    client.force_login(staff_user)
    state = StateFactory(code="NJ", name="New Jersey")
    county = CountyFactory(state=state, name="Cape May")
    place = PopulatedPlaceFactory(county=county, name="Cape May City")
    denomination = DenominationFactory(name="Analytics Baptist", family_relec="Baptist")
    schedule = CensusScheduleFactory(
        schedule_id="AN-001",
        county=county,
        populated_place=place,
        schedule_denomination=denomination,
        transcription_status="approved",
    )
    target = ReligiousBodyFactory(
        census_record=schedule,
        denomination=denomination,
        name="Analytics Target Church",
        num_edifices=2,
        edifice_value=Decimal("12345.67"),
    )
    ReligiousBodyFactory(name="Analytics Decoy Church")

    response = client.get(
        reverse("analytics:run_query"),
        {"family_relec": "Baptist", "state": "NJ"},
    )

    assert response.status_code == 200
    table_records = list(response.context["table"].data.data)
    assert [record.pk for record in table_records] == [target.pk]
    content = response.content.decode()
    assert "Analytics Target Church" in content
    assert "Analytics Decoy Church" not in content
    assert "Cape May City, Cape May, NJ" in content
    assert "$12,345.67" in content
    assert "Approved" in content
    assert "RelEc Family" in content
    assert "Baptist" in content


@pytest.mark.django_db
def test_analytics_table_sorting_and_pagination(client, staff_user):
    client.force_login(staff_user)
    for index in range(27):
        ReligiousBodyFactory(name=f"Church {index:02d}")

    first = client.get(reverse("analytics:run_query"), {"sort": "name"})
    second = client.get(
        reverse("analytics:run_query"),
        {"sort": "name", "page": 2},
    )

    first_rows = [row.record.name for row in first.context["table"].page.object_list]
    second_rows = [row.record.name for row in second.context["table"].page.object_list]
    assert first_rows == [f"Church {index:02d}" for index in range(25)]
    assert second_rows == ["Church 25", "Church 26"]
    assert "Page 2 of 2" in second.content.decode()


@pytest.mark.django_db
def test_analytics_csv_and_json_exports_contain_filtered_rows(client, staff_user):
    client.force_login(staff_user)
    state = StateFactory(code="MD", name="Maryland")
    county = CountyFactory(state=state, name="Montgomery")
    place = PopulatedPlaceFactory(county=county, name="Takoma Park")
    denomination = DenominationFactory(name="Export Baptist", family_relec="Baptist")
    schedule = CensusScheduleFactory(
        schedule_id="EXPORT-1",
        county=county,
        populated_place=place,
        schedule_denomination=denomination,
        transcription_status="approved",
    )
    ReligiousBodyFactory(
        census_record=schedule,
        denomination=denomination,
        name="Export Target Church",
        edifice_value=Decimal("500.00"),
    )
    ReligiousBodyFactory(name="Export Decoy Church")

    csv_response = client.get(
        reverse("analytics:run_query"),
        {"family_relec": "Baptist", "format": "csv"},
    )
    json_response = client.get(
        reverse("analytics:run_query"),
        {"family_relec": "Baptist", "format": "json"},
    )

    csv_content = csv_response.content.decode()
    assert csv_response["Content-Type"] == "text/csv"
    assert "Export Target Church" in csv_content
    assert "Export Decoy Church" not in csv_content
    assert json_response.json()["count"] == 1
    assert json_response.json()["results"][0] == {
        "schedule_id": "EXPORT-1",
        "religious_body_name": "Export Target Church",
        "denomination": "Export Baptist",
        "location": {
            "state": "MD",
            "county": "Montgomery",
            "place": "Takoma Park",
        },
        "address": None,
        "num_edifices": None,
        "edifice_value": 500.0,
        "transcription_status": "approved",
        "admin_url": f"/admin/census/censusschedule/{schedule.pk}/change/",
    }
