import pytest
from django.contrib.auth.models import User

from census.resources import CensusScheduleResource, DenominationResource
from tests.factories import ClergyFactory, MembershipFactory, ReligiousBodyFactory


@pytest.mark.django_db
def test_census_schedule_resource_exports_related_data(
    census_schedule, denomination
):
    census_schedule.assigned_transcriber = User.objects.create_user("transcriber")
    census_schedule.assigned_reviewer = User.objects.create_user("reviewer")
    census_schedule.save()

    ReligiousBodyFactory(
        census_record=census_schedule,
        denomination=denomination,
        name="First Church",
    )
    ReligiousBodyFactory(
        census_record=census_schedule,
        denomination=denomination,
        name="Second Church",
    )
    MembershipFactory(
        census_record=census_schedule,
        male_members=40,
        female_members=60,
        total_members_by_sex=100,
    )
    ClergyFactory(census_schedule=census_schedule, name="Rev. Ada Smith")
    ClergyFactory(census_schedule=census_schedule, name="Rev. Sam Jones")

    row = CensusScheduleResource().export([census_schedule]).dict[0]

    assert row["denomination_name"] == "Methodist; Methodist"
    assert row["church_name"] == "First Church; Second Church"
    assert row["location_city"] == "Falls Church"
    assert row["location_county"] == "Fairfax"
    assert row["location_state"] == "VA"
    assert row["total_members"] == 100
    assert row["male_members"] == 40
    assert row["female_members"] == 60
    assert row["clergy_names"] == "Rev. Ada Smith; Rev. Sam Jones"
    assert row["assigned_transcriber"] == "transcriber"
    assert row["assigned_reviewer"] == "reviewer"


@pytest.mark.django_db
def test_census_schedule_resource_exports_blanks_for_missing_related_data(
    census_schedule,
):
    row = CensusScheduleResource().export([census_schedule]).dict[0]

    assert row["denomination_name"] == ""
    assert row["church_name"] == ""
    assert row["total_members"] == ""
    assert row["male_members"] == ""
    assert row["female_members"] == ""
    assert row["clergy_names"] == ""
    assert row["assigned_transcriber"] == ""
    assert row["assigned_reviewer"] == ""


@pytest.mark.django_db
def test_denomination_resource_normalizes_empty_import_values():
    row = {
        "denomination_id": "  ",
        "published_churches_count": "NA",
    }

    DenominationResource().before_import_row(row)

    assert row["denomination_id"] is None
    assert row["published_churches_count"] is None


@pytest.mark.django_db
def test_denomination_resource_matches_by_id_then_falls_back_to_name(
    denomination,
):
    denomination.denomination_id = "METH-1"
    denomination.save()
    resource = DenominationResource()

    by_id = resource.get_instance(None, {"denomination_id": " METH-1 "})
    by_name = resource.get_instance(
        None,
        {"denomination_id": "", "denomination_name": " Methodist "},
    )
    missing = resource.get_instance(
        None,
        {"denomination_id": "UNKNOWN", "denomination_name": "Methodist"},
    )

    assert by_id == denomination
    assert by_name == denomination
    assert missing is None
