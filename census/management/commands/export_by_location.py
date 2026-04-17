"""
Management command to export census schedules by location.

Usage:
    # List all locations with schedule counts
    python manage.py export_by_location --list

    # Export by populated place ID
    python manage.py export_by_location --place-id 123 --format xlsx

    # Export by city name and state
    python manage.py export_by_location --city "Boston" --state "MA" --format csv

    # Export all schedules for a state
    python manage.py export_by_location --state "MA" --format xlsx
"""

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count

from census.models import CensusSchedule
from census.resources import CensusScheduleResource
from location.models import PopulatedPlace


class Command(BaseCommand):
    help = "Export census schedules by location to Excel, CSV, or JSON"

    def add_arguments(self, parser):
        parser.add_argument(
            "--list",
            action="store_true",
            help="List all locations with census schedule counts",
        )
        parser.add_argument(
            "--place-id",
            type=int,
            help="PopulatedPlace ID to export schedules for",
        )
        parser.add_argument(
            "--city",
            type=str,
            help="City name to filter by",
        )
        parser.add_argument(
            "--county",
            type=str,
            help="County name to filter by",
        )
        parser.add_argument(
            "--state",
            type=str,
            help="State code to filter by (e.g., MA, NY)",
        )
        parser.add_argument(
            "--format",
            type=str,
            choices=["xlsx", "csv", "json"],
            default="xlsx",
            help="Export format (default: xlsx)",
        )
        parser.add_argument(
            "--output",
            type=str,
            help="Output file path (optional, will auto-generate if not provided)",
        )

    def handle(self, *args, **options):
        # List mode
        if options["list"]:
            self.list_locations()
            return

        # Determine which filters to apply
        place_id = options.get("place_id")
        city = options.get("city")
        county = options.get("county")
        state = options.get("state")

        if not any([place_id, city, state]):
            raise CommandError(
                "You must provide at least one filter: --place-id, --city, --state, or use --list to see available locations"
            )

        # Get schedules based on filters
        schedules = self.get_schedules(place_id, city, county, state)

        if not schedules.exists():
            self.stdout.write(
                self.style.WARNING("No census schedules found matching the criteria.")
            )
            return

        # Generate output filename
        output_file = self.generate_filename(
            options["output"], options["format"], place_id, city, county, state
        )

        # Export the data
        self.export_schedules(schedules, output_file, options["format"])

    def list_locations(self):
        """List all populated places with census schedule counts"""
        self.stdout.write(self.style.SUCCESS("\nLocations with Census Schedules:"))
        self.stdout.write("=" * 80)

        places = (
            PopulatedPlace.objects.filter(census_schedules__isnull=False)
            .select_related("county__state")
            .annotate(schedule_count=Count("census_schedules", distinct=True))
            .order_by("county__state__code", "county__name", "name")
        )

        current_state = None
        for place in places:
            state_code = (
                place.county.state.code
                if place.county and place.county.state
                else "Unknown"
            )
            if state_code != current_state:
                current_state = state_code
                self.stdout.write(
                    f"\n{self.style.WARNING(current_state or 'Unknown State')}"
                )

            county_name = place.county.name if place.county else ""
            location_str = f"  ID: {place.id:<6} | {place.name}"
            if county_name:
                location_str += f", {county_name}"
            location_str += f" ({place.schedule_count} schedule"
            if place.schedule_count != 1:
                location_str += "s"
            location_str += ")"

            self.stdout.write(location_str)

        self.stdout.write("\n" + "=" * 80)
        self.stdout.write(f"\nTotal locations: {places.count()}\n")

    def get_schedules(self, place_id, city, county, state):
        """Get census schedules based on filter criteria"""
        queryset = CensusSchedule.objects.select_related(
            "county__state", "populated_place"
        ).prefetch_related(
            "church_details__denomination",
            "membership_details",
            "clergy",
        )

        # Build filters
        filters = {}
        if place_id:
            filters["populated_place__id"] = place_id
        else:
            if city:
                filters["populated_place__name__iexact"] = city
            if county:
                filters["county__name__iexact"] = county
            if state:
                filters["county__state__code__iexact"] = state

        return queryset.filter(**filters).distinct()

    def generate_filename(self, output_path, format, place_id, city, county, state):
        """Generate output filename based on filters"""
        if output_path:
            return output_path

        # Build filename from filters
        parts = ["census_schedules"]

        if place_id:
            parts.append(f"place_{place_id}")
        else:
            if city:
                parts.append(city.replace(" ", "_"))
            if county:
                parts.append(county.replace(" ", "_"))
            if state:
                parts.append(state)

        filename = "_".join(parts) + f".{format}"
        return filename

    def export_schedules(self, schedules, output_file, format):
        """Export schedules to file"""
        self.stdout.write(
            f"Exporting {schedules.count()} schedule(s) to {output_file}..."
        )

        resource = CensusScheduleResource()
        dataset = resource.export(schedules)

        # Write to file based on format
        with open(output_file, "wb") as f:
            if format == "csv":
                f.write(dataset.csv.encode("utf-8"))
            elif format == "json":
                f.write(dataset.json.encode("utf-8"))
            else:  # xlsx
                f.write(dataset.export("xlsx"))

        self.stdout.write(
            self.style.SUCCESS(f"✓ Successfully exported to {output_file}")
        )
