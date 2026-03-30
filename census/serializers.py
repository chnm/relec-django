from rest_framework import serializers

from .models import Denomination, Membership, ReligiousBody


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
    location_details = serializers.SerializerMethodField()
    denomination_details = DenominationSerializer(source="denomination", read_only=True)
    membership_details = serializers.SerializerMethodField()
    pastors = serializers.SerializerMethodField()
    finances = serializers.SerializerMethodField()
    urls = serializers.SerializerMethodField()
    transcription_status = serializers.SerializerMethodField()
    schedule_id = serializers.SerializerMethodField()

    class Meta:
        model = ReligiousBody
        fields = [
            "id",
            "name",
            "census_code",
            "division",
            "transcription_status",
            "schedule_id",
            "location_details",
            "denomination_details",
            "membership_details",
            "num_edifices",
            "has_pastors_residence",
            "finances",
            "pastors",
            "urls",
        ]

    def _decimal_to_float(self, value):
        """Convert a Decimal field value to a float, or None if null."""
        if value is not None:
            return float(value)
        return None

    def get_transcription_status(self, obj):
        if obj.census_record:
            return obj.census_record.transcription_status
        return None

    def get_schedule_id(self, obj):
        if obj.census_record:
            return obj.census_record.schedule_id
        return None

    def get_location_details(self, obj):
        if obj.census_record:
            pp = obj.census_record.populated_place
            county = obj.census_record.county
            return {
                "lat": pp.lat if pp else None,
                "lon": pp.lon if pp else None,
                "city_name": pp.name if pp else None,
                "map_name": pp.name if pp else None,
                "place_id": pp.place_id if pp else None,
                "county_name": county.name if county else None,
                "state_name": county.state.code if county and county.state else None,
                "address": obj.address,
                "urban_rural_code": obj.urban_rural_code,
            }
        return None

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
                    "total_members": total,
                    "members_under_13": membership.members_under_13 or 0,
                    "members_13_and_older": membership.members_13_and_older or 0,
                    "total_by_age": membership.total_members_by_age
                    or (
                        (membership.members_under_13 or 0)
                        + (membership.members_13_and_older or 0)
                    ),
                    "sunday_school_num_officers_teachers": membership.sunday_school_num_officers_teachers,
                    "sunday_school_num_scholars": membership.sunday_school_num_scholars,
                    "vbs_num_officers_teachers": membership.vbs_num_officers_teachers,
                    "vbs_num_scholars": membership.vbs_num_scholars,
                    "weekday_num_officers_teachers": membership.weekday_num_officers_teachers,
                    "weekday_num_scholars": membership.weekday_num_scholars,
                    "parochial_num_administrators": membership.parochial_num_administrators,
                    "parochial_num_elementary_teachers": membership.parochial_num_elementary_teachers,
                    "parochial_num_secondary_teachers": membership.parochial_num_secondary_teachers,
                    "parochial_num_elementary_scholars": membership.parochial_num_elementary_scholars,
                    "parochial_num_secondary_scholars": membership.parochial_num_secondary_scholars,
                }
        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.error(f"Error getting membership details for {obj}: {e}")
            return None
        return None

    def get_finances(self, obj):
        return {
            "expenditures": self._decimal_to_float(obj.expenses),
            "benevolences": self._decimal_to_float(obj.benevolences),
            "total_expenditures": self._decimal_to_float(obj.total_expenditures),
            "edifice_value": self._decimal_to_float(obj.edifice_value),
            "edifice_debt": self._decimal_to_float(obj.edifice_debt),
            "residence_value": self._decimal_to_float(obj.residence_value),
            "residence_debt": self._decimal_to_float(obj.residence_debt),
        }

    def get_urls(self, obj):
        request = self.context.get("request")
        base_url = request.build_absolute_uri("/") if request else ""
        base_url = base_url.rstrip("/")

        # URL to the individual schedule detail page
        schedule_url = None
        if obj.census_record:
            schedule_url = f"{base_url}/census/record/{obj.census_record.resource_id}/"

        # URL to the data table filtered by census family
        family_census_url = None
        if obj.denomination and obj.denomination.family_census:
            family_census_url = (
                f"{base_url}/census/browser/"
                f"?family={obj.denomination.family_census}"
            )

        # URL to the data table filtered by relec family and denomination
        family_relec_url = None
        if obj.denomination and obj.denomination.family_relec:
            family_relec_url = (
                f"{base_url}/census/browser/"
                f"?family={obj.denomination.family_relec}"
                f"&denomination={obj.denomination.id}"
            )

        return {
            "self": schedule_url,
            "family_census": family_census_url,
            "family_relec": family_relec_url,
        }

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
