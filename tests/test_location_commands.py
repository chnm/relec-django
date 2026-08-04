import json

import pytest
from django.core.management import call_command

from tests.factories import CountyFactory


def _write_omeka_cache(tmp_path, *items):
    cache_file = tmp_path / "omeka-cache.json"
    cache_file.write_text(json.dumps({"omeka_schedules": items}))
    return cache_file


@pytest.mark.django_db
def test_link_counties_from_cache_updates_matching_schedule(
    census_schedule, tmp_path
):
    target_county = CountyFactory(
        state=census_schedule.county.state,
        ahcb_id="target-county",
        name="Target County",
    )
    cache_file = _write_omeka_cache(
        tmp_path,
        {
            "omeka_id": census_schedule.resource_id,
            "ahcb_county_id": target_county.ahcb_id,
        },
    )

    call_command("link_counties_from_omeka", load_cache=str(cache_file))

    census_schedule.refresh_from_db()
    assert census_schedule.county == target_county


@pytest.mark.django_db
def test_link_counties_from_cache_dry_run_does_not_write(
    census_schedule, tmp_path
):
    original_county = census_schedule.county
    target_county = CountyFactory(
        state=original_county.state,
        ahcb_id="dry-run-target",
        name="Dry Run Target",
    )
    cache_file = _write_omeka_cache(
        tmp_path,
        {
            "omeka_id": census_schedule.resource_id,
            "ahcb_county_id": target_county.ahcb_id,
        },
    )

    call_command(
        "link_counties_from_omeka",
        load_cache=str(cache_file),
        dry_run=True,
    )

    census_schedule.refresh_from_db()
    assert census_schedule.county == original_county


@pytest.mark.django_db
def test_link_counties_only_missing_preserves_existing_assignment(
    census_schedule, tmp_path
):
    original_county = census_schedule.county
    target_county = CountyFactory(
        state=original_county.state,
        ahcb_id="only-missing-target",
        name="Only Missing Target",
    )
    cache_file = _write_omeka_cache(
        tmp_path,
        {
            "omeka_id": census_schedule.resource_id,
            "ahcb_county_id": target_county.ahcb_id,
        },
    )

    call_command(
        "link_counties_from_omeka",
        load_cache=str(cache_file),
        only_missing=True,
    )

    census_schedule.refresh_from_db()
    assert census_schedule.county == original_county


@pytest.mark.django_db
def test_link_counties_reports_unknown_county_without_changing_schedule(
    census_schedule, tmp_path, capsys
):
    original_county = census_schedule.county
    cache_file = _write_omeka_cache(
        tmp_path,
        {
            "omeka_id": census_schedule.resource_id,
            "ahcb_county_id": "unknown-county",
        },
    )

    call_command("link_counties_from_omeka", load_cache=str(cache_file))

    census_schedule.refresh_from_db()
    assert census_schedule.county == original_county
    assert "County AHCB ID not found:     1" in capsys.readouterr().out
