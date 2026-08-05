import factory
from factory.django import DjangoModelFactory

from census.models import (
    CensusSchedule,
    Clergy,
    Denomination,
    Membership,
    ReligiousBody,
    ScheduleTranscription,
    TranscriptionRun,
)
from location.models import County, PopulatedPlace, State


class StateFactory(DjangoModelFactory):
    class Meta:
        model = State
        django_get_or_create = ("code",)

    code = factory.Sequence(lambda n: f"S{n:01d}"[:2])
    name = factory.LazyAttribute(lambda o: f"State {o.code}")


class CountyFactory(DjangoModelFactory):
    class Meta:
        model = County

    ahcb_id = factory.Sequence(lambda n: f"ahcb_{n:04d}")
    name = factory.Sequence(lambda n: f"County {n}")
    state = factory.SubFactory(StateFactory)


class PopulatedPlaceFactory(DjangoModelFactory):
    class Meta:
        model = PopulatedPlace

    name = factory.Sequence(lambda n: f"Town {n}")
    county = factory.SubFactory(CountyFactory)


class DenominationFactory(DjangoModelFactory):
    class Meta:
        model = Denomination

    name = factory.Sequence(lambda n: f"Denomination {n}")
    family_relec = factory.Sequence(lambda n: f"Family {n % 3}")
    family_census = factory.Sequence(lambda n: f"Census Family {n % 3}")


class CensusScheduleFactory(DjangoModelFactory):
    class Meta:
        model = CensusSchedule

    resource_id = factory.Sequence(lambda n: n + 1000)
    schedule_title = factory.Sequence(lambda n: f"Schedule {n}")
    schedule_id = factory.Sequence(lambda n: f"sched-{n:04d}")
    county = factory.SubFactory(CountyFactory)
    populated_place = factory.SubFactory(PopulatedPlaceFactory)
    schedule_denomination = factory.SubFactory(DenominationFactory)


class TranscriptionRunFactory(DjangoModelFactory):
    class Meta:
        model = TranscriptionRun

    key = factory.Sequence(lambda n: f"transcription-run-{n}")
    kind = "agent"


class ScheduleTranscriptionFactory(DjangoModelFactory):
    class Meta:
        model = ScheduleTranscription

    census_schedule = factory.SubFactory(CensusScheduleFactory)
    run = factory.SubFactory(TranscriptionRunFactory)
    data = factory.LazyFunction(dict)


class ReligiousBodyFactory(DjangoModelFactory):
    class Meta:
        model = ReligiousBody

    census_record = factory.SubFactory(CensusScheduleFactory)
    denomination = factory.SubFactory(DenominationFactory)
    name = factory.Sequence(lambda n: f"Church {n}")


class MembershipFactory(DjangoModelFactory):
    class Meta:
        model = Membership

    census_record = factory.SubFactory(CensusScheduleFactory)
    total_members_by_sex = factory.Faker("random_int", min=10, max=500)


class ClergyFactory(DjangoModelFactory):
    class Meta:
        model = Clergy

    census_schedule = factory.SubFactory(CensusScheduleFactory)
    name = factory.Sequence(lambda n: f"Rev. Person {n}")
