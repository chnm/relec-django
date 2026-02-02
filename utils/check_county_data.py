#!/usr/bin/env python
"""
Check for data availability in a specific county.

Usage:
  poetry run python utils/check_county_data.py --state IL --county Hancock
  poetry run python utils/check_county_data.py --state VA --county "Fairfax"
"""

import argparse
import os

import django

from census.models import CensusSchedule, ReligiousBody
from location.models import Location

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()


def check_county_data(state_code, county_name):
    """Check if a county has location and religious body data."""

    print(f"\n{'=' * 60}")
    print(f"Data Check: {county_name} County, {state_code}")
    print(f"{'=' * 60}\n")

    # Check if locations exist
    locations = Location.objects.filter(state=state_code, county=county_name)
    location_count = locations.count()

    print(f"Location Records: {location_count}")
    if location_count > 0:
        cities = list(locations.values_list("city", flat=True).distinct()[:10])
        print(f"   Example cities: {', '.join(cities)}")
        if location_count > 10:
            print(f"   ... and {location_count - 10} more")
    else:
        print("   No location data found for this county")
        return

    print()

    # Check religious bodies
    bodies = ReligiousBody.objects.filter(
        location__state=state_code, location__county=county_name
    )
    body_count = bodies.count()

    print(f"Religious Bodies: {body_count}")
    if body_count > 0:
        print("   Sample records:")
        for body in bodies[:5]:
            denom = body.denomination.name if body.denomination else "Unknown"
            loc = (
                f"{body.location.city}, {body.location.state}"
                if body.location
                else "No location"
            )
            print(f"   - {body.name or 'Unnamed'} ({denom}) at {loc}")
        if body_count > 5:
            print(f"   ... and {body_count - 5} more")
    else:
        print("   No religious body data found for this county")

    print()

    # Check census schedules
    schedules = CensusSchedule.objects.filter(
        church_details__location__state=state_code,
        church_details__location__county=county_name,
    ).distinct()
    schedule_count = schedules.count()

    print(f"Census Schedules: {schedule_count}")
    if schedule_count > 0:
        print("   Schedules with churches in this county")
    else:
        print("   No census schedules found for this county")

    print()

    # Summary
    # print(f"{'='*60}")
    # if body_count > 0:
    #     print("VERDICT: County has complete data")
    # elif location_count > 0:
    #     print("VERDICT: County locations exist but NO religious body data")
    #     print("   This is likely a data gap in the original transcription.")
    # else:
    #     print("VERDICT: County not found in database")
    # print(f"{'='*60}\n")

    # Comparison with nearby counties
    if body_count == 0 and location_count > 0:
        print("Checking nearby counties for comparison:\n")
        nearby_counties = (
            Location.objects.filter(state=state_code)
            .values_list("county", flat=True)
            .distinct()[:5]
        )
        for nearby in nearby_counties:
            if nearby != county_name:
                nearby_count = ReligiousBody.objects.filter(
                    location__state=state_code, location__county=nearby
                ).count()
                status = "✓" if nearby_count > 0 else "✗"
                print(f"   {status} {nearby} County: {nearby_count} religious bodies")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Check data availability for a specific county",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  poetry run python utils/check_county_data.py --state IL --county Hancock
  poetry run python utils/check_county_data.py --state VA --county Fairfax
  poetry run python utils/check_county_data.py --state NY --county "New York"
        """,
    )
    parser.add_argument(
        "--state", required=True, help="Two-letter state code (e.g., IL, VA, NY)"
    )
    parser.add_argument(
        "--county", required=True, help="County name (e.g., Hancock, Fairfax)"
    )

    args = parser.parse_args()

    check_county_data(args.state.upper(), args.county)


if __name__ == "__main__":
    main()
