from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from datalayers.models import DataLayer
from tests.factories import (
    CensusScheduleFactory,
    DenominationFactory,
    ReligiousBodyFactory,
)
from visualizations.models import Visualization


@pytest.mark.django_db
def test_datalayer_geojson_returns_coordinates_metadata_and_finances(client):
    denomination = DenominationFactory(
        name="GeoJSON Baptist",
        family_relec="Baptist",
    )
    schedule = CensusScheduleFactory(
        resource_id=8080,
        schedule_denomination=denomination,
    )
    ReligiousBodyFactory(
        census_record=schedule,
        denomination=denomination,
        name="GeoJSON Congregation",
        num_edifices=2,
        edifice_value=Decimal("15000.00"),
        expenses=Decimal("900.50"),
    )
    DataLayer.objects.create(
        title="GeoJSON Point",
        source="geojson-test",
        lat=38.9,
        lon=-77.0,
        city="Washington",
        county="District of Columbia",
        state="DC",
        census_schedule=schedule,
        data={"historic_address": "1 Test Street"},
    )
    visualization = Visualization.objects.create(
        title="GeoJSON Test Map",
        slug="geojson-test-map",
        published_date=timezone.now(),
        render_type="datalayer",
        datalayer_source="geojson-test",
    )

    response = client.get(
        reverse("datalayer_geojson", args=[visualization.slug])
    )

    assert response.status_code == 200
    assert response.json() == {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [-77.0, 38.9]},
                "properties": {
                    "title": "GeoJSON Point",
                    "city": "Washington",
                    "county": "District of Columbia",
                    "state": "DC",
                    "historic_address": "1 Test Street",
                    "schedule_resource_id": 8080,
                    "denomination": "GeoJSON Baptist",
                    "denomination_id": denomination.pk,
                    "denomination_family": "Baptist",
                    "congregation_name": "GeoJSON Congregation",
                    "finances": {
                        "edifice_value": 15000.0,
                        "edifice_debt": None,
                        "residence_value": None,
                        "residence_debt": None,
                        "expenses": 900.5,
                        "benevolences": None,
                        "total_expenditures": None,
                    },
                    "num_edifices": 2,
                },
            }
        ],
    }


@pytest.mark.django_db
def test_datalayer_visualization_detail_embeds_populated_geojson(client):
    visualization = Visualization.objects.create(
        title="Embedded Data Layer",
        slug="embedded-data-layer",
        published_date=timezone.now(),
        render_type="datalayer",
        datalayer_source="embedded-source",
    )
    DataLayer.objects.create(
        title="Embedded Point",
        source="embedded-source",
        lat=40.0,
        lon=-75.0,
        city="Philadelphia",
        state="PA",
    )

    response = client.get(
        reverse("visualization-detail", args=[visualization.slug])
    )

    assert response.status_code == 200
    assert response.context["point_count"] == 1
    assert '"coordinates": [-75.0, 40.0]' in response.context["geojson_data"]
    content = response.content.decode()
    assert "Embedded Data Layer" in content
    assert "Embedded Point" in content
