"""
Management command to export census schedules by location.

Usage:
    # List all locations with schedule counts
    python manage.py export_by_location --list

    # Export by location ID
    python manage.py export_by_location --location-id 123 --format xlsx

    # Export by city and state
    python manage.py export_by_location --city "Boston" --state "MA" --format csv

    # Export all schedules for a state
    python manage.py export_by_location --state "MA" --format xlsx
"""

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count

from census.models import CensusSchedule
from census.resources import CensusScheduleResource
from location.models import Location


class Command(BaseCommand):
    help = "Export census schedules by location to Excel, CSV, or JSON"

    def add_arguments(self, parser):
        parser.add_argument(
            "--list",
            action="store_true",
            help="List all locations with census schedule counts",
        )
        parser.add_argument(
            "--location-id",
            type=int,
            help="Location ID to export schedules for",
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
        location_id = options.get("location_id")
        city = options.get("city")
        county = options.get("county")
        state = options.get("state")

        if not any([location_id, city, state]):
            raise CommandError(
                "You must provide at least one filter: --location-id, --city, --state, or use --list to see available locations"
            )

        # Get schedules based on filters
        schedules = self.get_schedules(location_id, city, county, state)

        if not schedules.exists():
            self.stdout.write(
                self.style.WARNING("No census schedules found matching the criteria.")
            )
            return

        # Generate output filename
        output_file = self.generate_filename(
            options["output"], options["format"], location_id, city, county, state
        )

        # Export the data
        self.export_schedules(schedules, output_file, options["format"])

    def list_locations(self):
        """List all locations with census schedule counts"""
        self.stdout.write(self.style.SUCCESS("\nLocations with Census Schedules:"))
        self.stdout.write("=" * 80)

        locations = (
            Location.objects.filter(religiousbody__census_record__isnull=False)
            .annotate(
                schedule_count=Count("religiousbody__census_record", distinct=True)
            )
            .order_by("state", "county", "city")
        )

        current_state = None
        for location in locations:
            if location.state != current_state:
                current_state = location.state
                self.stdout.write(
                    f"\n{self.style.WARNING(current_state or 'Unknown State')}"
                )

            location_str = f"  ID: {location.id:<6} | {location.city}"
            if location.county:
                location_str += f", {location.county}"
            location_str += f" ({location.schedule_count} schedule"
            if location.schedule_count != 1:
                location_str += "s"
            location_str += ")"

            self.stdout.write(location_str)

        self.stdout.write("\n" + "=" * 80)
        self.stdout.write(f"\nTotal locations: {locations.count()}\n")

    def get_schedules(self, location_id, city, county, state):
        """Get census schedules based on filter criteria"""
        queryset = CensusSchedule.objects.select_related().prefetch_related(
            "church_details__denomination",
            "church_details__location",
            "membership_details",
            "clergy",
        )

        # Build filters
        filters = {}
        if location_id:
            filters["church_details__location__id"] = location_id
        else:
            if city:
                filters["church_details__location__city__iexact"] = city
            if county:
                filters["church_details__location__county__iexact"] = county
            if state:
                filters["church_details__location__state__iexact"] = state

        return queryset.filter(**filters).distinct()

    def generate_filename(self, output_path, format, location_id, city, county, state):
        """Generate output filename based on filters"""
        if output_path:
            return output_path

        # Build filename from filters
        parts = ["census_schedules"]

        if location_id:
            parts.append(f"loc_{location_id}")
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
