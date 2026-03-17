from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand

from census.models import CensusSchedule, Clergy, Membership, ReligiousBody
from location.models import County, PopulatedPlace, State
from pages.models import BlogPost, Page, Visualization


class Command(BaseCommand):
    help = "Set up user groups and permissions for transcription project management"

    def handle(self, *args, **options):
        # Get content types
        census_ct = ContentType.objects.get_for_model(CensusSchedule)
        religious_body_ct = ContentType.objects.get_for_model(ReligiousBody)
        membership_ct = ContentType.objects.get_for_model(Membership)
        clergy_ct = ContentType.objects.get_for_model(Clergy)
        state_ct = ContentType.objects.get_for_model(State)
        county_ct = ContentType.objects.get_for_model(County)
        place_ct = ContentType.objects.get_for_model(PopulatedPlace)
        blogpost_ct = ContentType.objects.get_for_model(BlogPost)
        page_ct = ContentType.objects.get_for_model(Page)
        viz_ct = ContentType.objects.get_for_model(Visualization)

        # Create Transcribers group (students)
        transcribers_group, created = Group.objects.get_or_create(name="Transcribers")
        if created:
            self.stdout.write(self.style.SUCCESS('Created "Transcribers" group'))

        # Add permissions for transcribers (can add/change census data but not delete;
        # read-only access to location data and content management)
        transcriber_permissions = [
            # Census schedules
            Permission.objects.get(
                content_type=census_ct, codename="view_censusschedule"
            ),
            Permission.objects.get(
                content_type=census_ct, codename="change_censusschedule"
            ),
            # Religious bodies
            Permission.objects.get(
                content_type=religious_body_ct, codename="add_religiousbody"
            ),
            Permission.objects.get(
                content_type=religious_body_ct, codename="view_religiousbody"
            ),
            Permission.objects.get(
                content_type=religious_body_ct, codename="change_religiousbody"
            ),
            # Membership
            Permission.objects.get(
                content_type=membership_ct, codename="add_membership"
            ),
            Permission.objects.get(
                content_type=membership_ct, codename="view_membership"
            ),
            Permission.objects.get(
                content_type=membership_ct, codename="change_membership"
            ),
            # Clergy
            Permission.objects.get(content_type=clergy_ct, codename="add_clergy"),
            Permission.objects.get(content_type=clergy_ct, codename="view_clergy"),
            Permission.objects.get(content_type=clergy_ct, codename="change_clergy"),
            # Location data (read-only)
            Permission.objects.get(content_type=state_ct, codename="view_state"),
            Permission.objects.get(content_type=county_ct, codename="view_county"),
            Permission.objects.get(content_type=place_ct, codename="view_populatedplace"),
            # Content management (read-only)
            Permission.objects.get(content_type=blogpost_ct, codename="view_blogpost"),
            Permission.objects.get(content_type=page_ct, codename="view_page"),
            Permission.objects.get(content_type=viz_ct, codename="view_visualization"),
        ]
        transcribers_group.permissions.set(transcriber_permissions)

        # Create Reviewers group (PIs and senior staff)
        reviewers_group, created = Group.objects.get_or_create(name="Reviewers")
        if created:
            self.stdout.write(self.style.SUCCESS('Created "Reviewers" group'))

        # Add all permissions for reviewers
        reviewer_permissions = Permission.objects.filter(
            content_type__in=[census_ct, religious_body_ct, membership_ct, clergy_ct]
        )
        reviewers_group.permissions.set(reviewer_permissions)

        self.stdout.write(
            self.style.SUCCESS(
                "Successfully set up transcription groups and permissions"
            )
        )
        self.stdout.write("")
        self.stdout.write("Next steps:")
        self.stdout.write('1. Add student users to the "Transcribers" group')
        self.stdout.write('2. Add PI/staff users to the "Reviewers" group')
        self.stdout.write(
            "3. Run migrations: python manage.py makemigrations && python manage.py migrate"
        )
