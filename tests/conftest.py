import pytest
from django.core.cache import cache as django_cache

from .factories import (
    CensusScheduleFactory,
    CountyFactory,
    DenominationFactory,
    MembershipFactory,
    PopulatedPlaceFactory,
    ReligiousBodyFactory,
    StateFactory,
)


@pytest.fixture(autouse=True)
def _clear_cache():
    """Clear cache before and after every test to avoid cross-test pollution."""
    django_cache.clear()
    yield
    django_cache.clear()


@pytest.fixture
def state():
    return StateFactory(code="VA", name="Virginia")


@pytest.fixture
def second_state():
    return StateFactory(code="NJ", name="New Jersey")


@pytest.fixture
def county(state):
    return CountyFactory(state=state, name="Fairfax")


@pytest.fixture
def second_county(second_state):
    return CountyFactory(state=second_state, name="Cape May")


@pytest.fixture
def populated_place(county):
    return PopulatedPlaceFactory(county=county, name="Falls Church")


@pytest.fixture
def denomination():
    return DenominationFactory(name="Methodist", family_relec="Methodist")


@pytest.fixture
def second_denomination():
    return DenominationFactory(name="Baptist", family_relec="Baptist")


@pytest.fixture
def census_schedule(county, populated_place, denomination):
    return CensusScheduleFactory(
        county=county,
        populated_place=populated_place,
        schedule_denomination=denomination,
    )


@pytest.fixture
def census_schedule_with_membership(census_schedule):
    MembershipFactory(census_record=census_schedule, total_members_by_sex=150)
    return census_schedule


@pytest.fixture
def religious_body(census_schedule, denomination):
    return ReligiousBodyFactory(
        census_record=census_schedule,
        denomination=denomination,
    )


@pytest.fixture
def sample_dataset(state, second_state, denomination, second_denomination):
    """Create a small dataset with multiple states, counties, and schedules."""
    county_va = CountyFactory(state=state, name="Fairfax")
    county_nj = CountyFactory(state=second_state, name="Cape May")

    place_va = PopulatedPlaceFactory(county=county_va, name="Falls Church")
    place_nj = PopulatedPlaceFactory(county=county_nj, name="Cape May City")

    schedules = []
    for i in range(3):
        s = CensusScheduleFactory(
            county=county_va,
            populated_place=place_va,
            schedule_denomination=denomination,
        )
        ReligiousBodyFactory(census_record=s, denomination=denomination)
        schedules.append(s)

    for i in range(2):
        s = CensusScheduleFactory(
            county=county_nj,
            populated_place=place_nj,
            schedule_denomination=second_denomination,
        )
        ReligiousBodyFactory(census_record=s, denomination=second_denomination)
        schedules.append(s)

    return {
        "states": [state, second_state],
        "counties": [county_va, county_nj],
        "places": [place_va, place_nj],
        "denominations": [denomination, second_denomination],
        "schedules": schedules,
    }
