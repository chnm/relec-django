from rest_framework import serializers

from .models import CensusSchedule, Clergy, Denomination, Membership, ReligiousBody


class DenominationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Denomination
        fields = ["id", "denomination_id", "name", "family_census", "family_relec"]


class MembershipSerializer(serializers.ModelSerializer):
    total_members = serializers.IntegerField(
        source="total_members_by_sex", read_only=True
    )
    total_by_age = serializers.IntegerField(source="total_members_by_age", read_only=True)

    class Meta:
        model = Membership
        fields = [
            "male_members",
            "female_members",
            "total_members",
            "members_under_13",
            "members_13_and_older",
            "total_by_age",
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


class ClergySerializer(serializers.ModelSerializer):
    class Meta:
        model = Clergy
        fields = [
            "name",
            "is_assistant",
            "college",
            "theological_seminary",
            "num_other_churches_served",
            "serving_congregation",
        ]


class TranscriptionSerializer(serializers.ModelSerializer):
    status = serializers.CharField(source="transcription_status", read_only=True)
    ai = serializers.JSONField(source="ai_transcription", read_only=True)
    human = serializers.JSONField(source="human_transcription", read_only=True)
    ai_notes = serializers.SerializerMethodField()

    class Meta:
        model = CensusSchedule
        fields = ["status", "ai", "human", "ai_notes"]

    def get_ai_notes(self, obj):
        return obj.ai_notes or None


class TranscriptionMapSerializer(serializers.ModelSerializer):
    status = serializers.CharField(source="transcription_status", read_only=True)

    class Meta:
        model = CensusSchedule
        fields = ["status"]


class ReligiousBodySerializer(serializers.ModelSerializer):
    transcription = TranscriptionSerializer(source="census_record", read_only=True)
    location_details = serializers.SerializerMethodField()
    denomination_details = DenominationSerializer(source="denomination", read_only=True)
    membership_details = serializers.SerializerMethodField()
    pastors = serializers.SerializerMethodField()
    finances = serializers.SerializerMethodField()
    urls = serializers.SerializerMethodField()
    schedule_id = serializers.SerializerMethodField()
    has_location = serializers.SerializerMethodField()

    num_assistant_pastors = serializers.SerializerMethodField()
    respondent = serializers.SerializerMethodField()
    processing = serializers.SerializerMethodField()
    marginalia = serializers.SerializerMethodField()

    class Meta:
        model = ReligiousBody
        fields = [
            "id",
            "name",
            "census_code",
            "division",
            "schedule_id",
            "transcription",
            "has_location",
            "location_details",
            "denomination_details",
            "membership_details",
            "num_edifices",
            "has_pastors_residence",
            "finances",
            "pastors",
            "num_assistant_pastors",
            "respondent",
            "processing",
            "marginalia",
            "urls",
        ]

    def _decimal_to_float(self, value):
        """Convert a Decimal field value to a float, or None if null."""
        if value is not None:
            return float(value)
        return None

    def get_has_location(self, obj):
        return (
            obj.census_record is not None
            and obj.census_record.populated_place is not None
        )

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
                "county_ahcb": county.ahcb_id if county else None,
                "county_name": county.name if county else None,
                "state_name": county.state.code if county and county.state else None,
                "address": obj.address,
                "urban_rural_code": obj.urban_rural_code,
            }
        return None

    def get_membership_details(self, obj):
        memberships = getattr(obj, "_api_memberships", [])
        if not memberships:
            return None
        return MembershipSerializer(memberships[0]).data

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

        # Image URL from object storage
        image_url = None
        if obj.census_record and obj.census_record.original_image:
            image_url = obj.census_record.original_image.url

        return {
            "self": schedule_url,
            "image": image_url,
            "family_census": family_census_url,
            "family_relec": family_relec_url,
        }

    def get_pastors(self, obj):
        clergy = getattr(obj.census_record, "_api_clergy", [])
        if not clergy:
            return None
        return ClergySerializer(clergy, many=True).data

    def get_num_assistant_pastors(self, obj):
        if obj.census_record:
            return obj.census_record.num_assistant_pastors
        return None

    def get_respondent(self, obj):
        if not obj.census_record:
            return None
        cs = obj.census_record
        if not any([cs.respondent_name, cs.respondent_title, cs.respondent_po_address, cs.respondent_date_signed]):
            return None
        return {
            "name": cs.respondent_name or None,
            "title": cs.respondent_title or None,
            "po_address": cs.respondent_po_address or None,
            "date_signed": cs.respondent_date_signed or None,
        }

    def get_processing(self, obj):
        if not obj.census_record:
            return None
        cs = obj.census_record
        if not any([cs.date_received, cs.district_stamp, cs.denomination_code_stamp]):
            return None
        return {
            "date_received": cs.date_received.isoformat() if cs.date_received else None,
            "district_stamp": cs.district_stamp or None,
            "denomination_code_stamp": cs.denomination_code_stamp or None,
        }

    def get_marginalia(self, obj):
        if obj.census_record:
            return obj.census_record.marginalia or None
        return None


class ReligiousBodyMapSerializer(ReligiousBodySerializer):
    """Reduced religious-body representation for high-volume map requests."""

    transcription = TranscriptionMapSerializer(source="census_record", read_only=True)

    class Meta(ReligiousBodySerializer.Meta):
        fields = [
            "id",
            "name",
            "census_code",
            "division",
            "schedule_id",
            "transcription",
            "has_location",
            "location_details",
            "denomination_details",
            "membership_details",
            "num_edifices",
            "has_pastors_residence",
            "finances",
            "urls",
        ]
