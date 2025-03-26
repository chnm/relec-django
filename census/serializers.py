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
    state_name = serializers.CharField(source="state.name", read_only=True)
    county_name = serializers.CharField(source="county.name", read_only=True)
    city_name = serializers.CharField(source="city.name", read_only=True)

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
        fields = ["id", "denomination_id", "name", "family_census", "family_arda"]


class MembershipSerializer(serializers.ModelSerializer):
    class Meta:
        model = Membership
        fields = [
            "male_members",
            "female_members",
            "members_under_13",
            "members_13_and_older",
            "sunday_school_num_officers_teachers",
            "sunday_school_num_scholars",
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
            "membership_details",
            "total_members",
            "num_edifices",
            "edifice_value",
            "expenses",
            "pastors",
        ]

    def get_membership_details(self, obj):
        try:
            membership = Membership.objects.filter(religious_body=obj).first()
            if membership:
                return {
                    "male_members": membership.male_members,
                    "female_members": membership.female_members,
                    "total": membership.male_members + membership.female_members,
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
                return membership.male_members + membership.female_members
        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.error(f"Error getting total members for {obj}: {e}")
            return None
        return 0

    def get_pastors(self, obj):
        try:
            clergy = obj.census_record.clergy.filter(is_assistant=False).first()
            return clergy.name if clergy else ""
        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.error(f"Error getting pastor for {obj}: {e}")
            return ""
