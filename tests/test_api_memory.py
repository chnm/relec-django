from urllib.parse import urlsplit

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from census.models import ReligiousBody
from tests.factories import CensusScheduleFactory


@pytest.mark.django_db
@pytest.mark.parametrize("view", [None, "map"])
def test_api_does_not_load_unused_legacy_transcriptions(client, view):
    schedule = CensusScheduleFactory(
        ai_transcription={"notes": "Unused legacy AI transcription"},
        human_transcription={"notes": "Unused legacy human transcription"},
    )
    ReligiousBody.objects.create(census_record=schedule, name="Example Church")

    with CaptureQueriesContext(connection) as queries:
        response = client.get(
            reverse("religiousbody-list"), {"view": view} if view else {}
        )

    assert response.status_code == 200
    assert len(response.json()["results"]) == 1
    assert not any('"ai_transcription"' in query["sql"] for query in queries)
    assert not any('"human_transcription"' in query["sql"] for query in queries)


@pytest.mark.django_db
@pytest.mark.parametrize("view", [None, "map"])
@pytest.mark.parametrize(
    "params,accept,expected_size",
    [
        ({"format": "api", "page_size": 5000}, "*/*", 100),
        ({"page_size": 5000}, "text/html", 100),
        ({"format": "api", "page_size": 5}, "text/html", 5),
        ({"format": "json", "page_size": 5000}, "*/*", 125),
        ({"page_size": 5000}, "application/json", 125),
    ],
)
def test_html_preview_is_bounded_without_reducing_json_pages(
    client, view, params, accept, expected_size
):
    schedule = CensusScheduleFactory()
    ReligiousBody.objects.bulk_create(
        [
            ReligiousBody(census_record=schedule, name=f"Church {index:03d}")
            for index in range(125)
        ]
    )
    params = {**params, "ordering": "name"}
    if view:
        params["view"] = view

    response = client.get(reverse("religiousbody-list"), params, HTTP_ACCEPT=accept)

    assert response.status_code == 200
    assert response.data["count"] == 125
    assert len(response.data["results"]) == expected_size
    if expected_size < 125:
        next_url = urlsplit(response.data["next"])
        next_page = client.get(f"{next_url.path}?{next_url.query}", HTTP_ACCEPT=accept)
        assert next_page.status_code == 200
        assert len(next_page.data["results"]) == min(expected_size, 125 - expected_size)
        assert {row["id"] for row in response.data["results"]}.isdisjoint(
            row["id"] for row in next_page.data["results"]
        )
    else:
        assert response.data["next"] is None
