from urllib.parse import urlencode

import pytest
from django.conf import settings
from django.contrib.sessions.backends.db import SessionStore
from django.urls import reverse
from django.utils import timezone

from tests.factories import (
    CensusScheduleFactory,
    CountyFactory,
    DenominationFactory,
    PopulatedPlaceFactory,
    ReligiousBodyFactory,
    StateFactory,
)
from visualizations.models import Visualization


def _authenticate_page(page, live_server, user):
    session = SessionStore()
    session["_auth_user_id"] = str(user.pk)
    session["_auth_user_backend"] = "django.contrib.auth.backends.ModelBackend"
    session["_auth_user_hash"] = user.get_session_auth_hash()
    session.save()
    page.context.add_cookies(
        [
            {
                "name": settings.SESSION_COOKIE_NAME,
                "value": session.session_key,
                "url": live_server.url,
            }
        ]
    )


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_browser_census_filters_render_only_matching_cards(page, live_server):
    baptist = DenominationFactory(name="Browser E2E Baptist", family_relec="Baptist")
    methodist = DenominationFactory(
        name="Browser E2E Methodist",
        family_relec="Methodist",
    )
    target = CensusScheduleFactory(
        schedule_title="Browser Target Schedule",
        schedule_denomination=baptist,
    )
    ReligiousBodyFactory(
        census_record=target,
        denomination=baptist,
        name="Browser Target Congregation",
    )
    decoy = CensusScheduleFactory(
        schedule_title="Browser Decoy Schedule",
        schedule_denomination=methodist,
    )
    ReligiousBodyFactory(
        census_record=decoy,
        denomination=methodist,
        name="Browser Decoy Congregation",
    )

    url = f"{live_server.url}{reverse('census_browser')}?{urlencode({'family': 'Baptist'})}"
    page.goto(url, wait_until="domcontentloaded")

    assert page.get_by_text("Browser Target Schedule").is_visible()
    assert page.get_by_text("Browser Target Congregation").is_visible()
    assert page.get_by_text("Browser Decoy Schedule").count() == 0
    assert page.get_by_text("Browser Decoy Congregation").count() == 0


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_browser_analytics_table_renders_filtered_data(
    page,
    live_server,
    django_user_model,
):
    user = django_user_model.objects.create_user(
        username="browser-reviewer",
        password="local-test-password",
        is_staff=True,
    )
    denomination = DenominationFactory(
        name="Browser Analytics Baptist",
        family_relec="Baptist",
    )
    schedule = CensusScheduleFactory(
        schedule_id="BROWSER-AN-1",
        schedule_denomination=denomination,
        transcription_status="approved",
    )
    ReligiousBodyFactory(
        census_record=schedule,
        denomination=denomination,
        name="Browser Analytics Target",
    )
    ReligiousBodyFactory(name="Browser Analytics Decoy")
    _authenticate_page(page, live_server, user)

    url = (
        f"{live_server.url}{reverse('analytics:run_query')}?"
        f"{urlencode({'family_relec': 'Baptist'})}"
    )
    page.goto(url, wait_until="domcontentloaded")

    table = page.locator("table")
    assert table.get_by_text("Browser Analytics Target").is_visible()
    assert table.get_by_text("BROWSER-AN-1").is_visible()
    assert table.get_by_text("Approved").is_visible()
    assert table.get_by_text("Browser Analytics Decoy").count() == 0
    assert page.get_by_text("Found 1 result").is_visible()


@pytest.mark.e2e
@pytest.mark.django_db(transaction=True)
def test_browser_leaflet_visualization_populates_from_api(page, live_server):
    state = StateFactory(code="CT", name="Connecticut")
    county = CountyFactory(state=state, name="Hartford")
    place = PopulatedPlaceFactory(
        county=county,
        name="Hartford",
        place_id=9001,
        lat=41.7658,
        lon=-72.6734,
    )
    denomination = DenominationFactory(
        name="Browser Map Baptist",
        family_census="Baptist bodies",
        family_relec="Baptist",
    )
    schedule = CensusScheduleFactory(
        county=county,
        populated_place=place,
        schedule_denomination=denomination,
        transcription_status="approved",
    )
    ReligiousBodyFactory(
        census_record=schedule,
        denomination=denomination,
        name="Browser Map Congregation",
    )
    visualization = Visualization.objects.create(
        title="Browser Denomination Map",
        slug="browser-denomination-map",
        published_date=timezone.now(),
        render_type="custom",
        custom_view_name="denomination_geojson_map",
    )
    page.route("**.basemaps.cartocdn.com/**", lambda route: route.abort())
    page_errors = []
    page.on("pageerror", lambda error: page_errors.append(str(error)))

    page.goto(
        f"{live_server.url}{reverse('visualization-detail', args=[visualization.slug])}",
        wait_until="domcontentloaded",
    )

    page.locator("#placeCount").wait_for(state="visible")
    page.locator("#placeCount").filter(has_text="1").wait_for()
    page.locator("#congregationCount").filter(has_text="1").wait_for()
    marker = page.locator("#map path.leaflet-interactive").first
    marker.wait_for(state="visible")
    marker.click(force=True)
    assert page.locator("#detailsContent").get_by_text(
        "Browser Map Congregation"
    ).is_visible()
    assert page.locator("#detailsContent").get_by_text(
        "Browser Map Baptist"
    ).is_visible()
    assert page_errors == []
