from rest_framework import serializers

from location.models import Location

from .models import Denomination, Membership, ReligiousBody


class MapMarkerSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer specifically for map marker data.
    Only includes fields needed for map display to reduce overhead.
    """

    # Location data
    lat = serializers.SerializerMethodField()
    lon = serializers.SerializerMethodField()

    # Denomination data
    family = serializers.SerializerMethodField()
    denomination_name = serializers.SerializerMethodField()

    # Total members field
    total_members = serializers.IntegerField(default=0)

    class Meta:
        model = ReligiousBody
        fields = [
            "id",
            "name",
            "lat",
            "lon",
            "family",
            "denomination_name",
            "total_members",
        ]

    def get_lat(self, obj):
        if obj.location:
            return obj.location.lat
        return None

    def get_lon(self, obj):
        if obj.location:
            return obj.location.lon
        return None

    def get_family(self, obj):
        if obj.denomination:
            return obj.denomination.family_census
        return "Unknown"

    def get_denomination_name(self, obj):
        if obj.denomination:
            return obj.denomination.name
        return "Unknown"


class LocationSerializer(serializers.ModelSerializer):
    # Direct mapping to string fields in the Location model
    state_name = serializers.CharField(source="state", read_only=True)
    county_name = serializers.CharField(source="county", read_only=True)
    city_name = serializers.CharField(source="city", read_only=True)

    class Meta:
        model = Location
        fields = [
            "id",
            "place_id",
            "lat",
            "lon",
            "map_name",
            "state_name",
            "county_name",
            "city_name",
        ]


class DenominationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Denomination
        fields = ["id", "denomination_id", "name", "family_census", "family_relec"]


class MembershipSerializer(serializers.ModelSerializer):
    class Meta:
        model = Membership
        fields = [
            "male_members",
            "female_members",
            "total_members_by_sex",
            "members_under_13",
            "members_13_and_older",
            "total_members_by_age",
            "sunday_school_num_officers_teachers",
            "sunday_school_num_scholars",
            "vbs_num_officers_teachers",
            "vbs_num_scholars",
            "weekday_num_officers_teachers",
            "weekday_num_scholars",
            "parochial_num_administrators",
            "parochial_num_elementary_teachers",
            "parochial_num_secondary_teachers",
            "parochial_num_elementary_scholars",
            "parochial_num_secondary_scholars",
        ]


class ReligiousBodySerializer(serializers.ModelSerializer):
    location_details = LocationSerializer(source="location", read_only=True)
    denomination_details = DenominationSerializer(source="denomination", read_only=True)
    membership_details = serializers.SerializerMethodField()
    pastors = serializers.SerializerMethodField()
    total_members = serializers.SerializerMethodField()

    class Meta:
        model = ReligiousBody
        fields = [
            "id",
            "name",
            "census_code",
            "division",
            "location_details",
            "denomination_details",
            "address",
            "urban_rural_code",
            "membership_details",
            "total_members",
            "num_edifices",
            "edifice_value",
            "edifice_debt",
            "has_pastors_residence",
            "residence_value",
            "residence_debt",
            "expenses",
            "benevolences",
            "total_expenditures",
            "pastors",
        ]

    def get_membership_details(self, obj):
        try:
            membership = Membership.objects.filter(religious_body=obj).first()
            if membership:
                # Handle NULL values properly
                male = membership.male_members or 0
                female = membership.female_members or 0

                # Use recorded total if available, otherwise calculate
                if membership.total_members_by_sex is not None:
                    total = membership.total_members_by_sex
                else:
                    total = male + female

                return {
                    "male_members": male,
                    "female_members": female,
                    "total": total,
                    "members_under_13": membership.members_under_13 or 0,
                    "members_13_and_older": membership.members_13_and_older or 0,
                    "total_by_age": membership.total_members_by_age
                    or (
                        (membership.members_under_13 or 0)
                        + (membership.members_13_and_older or 0)
                    ),
                }
        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.error(f"Error getting membership details for {obj}: {e}")
            return None
        return None

    def get_total_members(self, obj):
        try:
            membership = Membership.objects.filter(religious_body=obj).first()
            if membership:
                # Use recorded total if available
                if membership.total_members_by_sex is not None:
                    return membership.total_members_by_sex

                # Otherwise calculate from male/female counts
                male = membership.male_members or 0
                female = membership.female_members or 0
                return male + female
        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.error(f"Error getting total members for {obj}: {e}")
            return None
        return 0

    def get_pastors(self, obj):
        try:
            clergy = obj.census_record.clergy.filter(is_assistant=False).first()
            if clergy:
                return {
                    "name": clergy.name,
                    "is_assistant": clergy.is_assistant,
                    "college": clergy.college,
                    "theological_seminary": clergy.theological_seminary,
                    "num_other_churches_served": clergy.num_other_churches_served,
                    "serving_congregation": clergy.serving_congregation,
                }
            return None
        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.error(f"Error getting pastor for {obj}: {e}")
            return None
