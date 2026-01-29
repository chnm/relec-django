"""
Import/Export resources for census data.
"""

from import_export import fields, resources

from .models import CensusSchedule


class CensusScheduleResource(resources.ModelResource):
    """Resource for exporting CensusSchedule data."""

    # Related fields - using custom dehydrate methods
    denomination_name = fields.Field(column_name="denomination_name")
    location_city = fields.Field(column_name="location_city")
    location_county = fields.Field(column_name="location_county")
    location_state = fields.Field(column_name="location_state")

    # Church details
    church_name = fields.Field(column_name="church_name")

    # Membership details
    total_members = fields.Field(column_name="total_members")
    male_members = fields.Field(column_name="male_members")
    female_members = fields.Field(column_name="female_members")

    # Clergy
    clergy_names = fields.Field(column_name="clergy_names")

    class Meta:
        model = CensusSchedule
        fields = (
            "id",
            "resource_id",
            "schedule_id",
            "schedule_title",
            "denomination_name",
            "church_name",
            "location_city",
            "location_county",
            "location_state",
            "total_members",
            "male_members",
            "female_members",
            "clergy_names",
            "original_image",
            "transcription_status",
            "assigned_transcriber",
            "assigned_reviewer",
            "notes",
            "created_at",
            "updated_at",
        )
        export_order = fields

    def dehydrate_denomination_name(self, schedule):
        """Get denomination names from all related religious bodies."""
        denominations = []
        for rb in schedule.church_details.all():
            if rb.denomination:
                denominations.append(rb.denomination.name)
        return "; ".join(denominations) if denominations else ""

    def dehydrate_church_name(self, schedule):
        """Get church names from all related religious bodies."""
        names = []
        for rb in schedule.church_details.all():
            if rb.name:
                names.append(rb.name)
        return "; ".join(names) if names else ""

    def dehydrate_location_city(self, schedule):
        """Get cities from all related religious bodies."""
        cities = []
        for rb in schedule.church_details.all():
            if rb.location and rb.location.city:
                cities.append(rb.location.city)
        return "; ".join(set(cities)) if cities else ""

    def dehydrate_location_county(self, schedule):
        """Get counties from all related religious bodies."""
        counties = []
        for rb in schedule.church_details.all():
            if rb.location and rb.location.county:
                counties.append(rb.location.county)
        return "; ".join(set(counties)) if counties else ""

    def dehydrate_location_state(self, schedule):
        """Get states from all related religious bodies."""
        states = []
        for rb in schedule.church_details.all():
            if rb.location and rb.location.state:
                states.append(rb.location.state)
        return "; ".join(set(states)) if states else ""

    def dehydrate_total_members(self, schedule):
        """Get total members from membership details."""
        memberships = schedule.membership_details.all()
        if memberships:
            return memberships.first().total_members_by_sex
        return ""

    def dehydrate_male_members(self, schedule):
        """Get male members from membership details."""
        memberships = schedule.membership_details.all()
        if memberships:
            return memberships.first().male_members
        return ""

    def dehydrate_female_members(self, schedule):
        """Get female members from membership details."""
        memberships = schedule.membership_details.all()
        if memberships:
            return memberships.first().female_members
        return ""

    def dehydrate_clergy_names(self, schedule):
        """Get clergy names."""
        clergy = []
        for c in schedule.clergy.all():
            if c.name:
                clergy.append(c.name)
        return "; ".join(clergy) if clergy else ""

    def dehydrate_assigned_transcriber(self, schedule):
        """Return username of assigned transcriber."""
        if schedule.assigned_transcriber:
            return schedule.assigned_transcriber.username
        return ""

    def dehydrate_assigned_reviewer(self, schedule):
        """Return username of assigned reviewer."""
        if schedule.assigned_reviewer:
            return schedule.assigned_reviewer.username
        return ""
