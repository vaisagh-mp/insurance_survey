from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Claim, Insurer, Insured, Policy, SurveyAssignment, Priority

User = get_user_model()


class InsurerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Insurer
        fields = '__all__'


class InsuredSerializer(serializers.ModelSerializer):
    class Meta:
        model = Insured
        fields = '__all__'


class PolicySerializer(serializers.ModelSerializer):
    insurer_name = serializers.CharField(source='insurer.company_name', read_only=True)

    class Meta:
        model = Policy
        fields = '__all__'


class SurveyAssignmentSerializer(serializers.ModelSerializer):
    surveyor_username = serializers.CharField(source='surveyor.username', read_only=True)
    surveyor_name = serializers.SerializerMethodField()
    assigned_by_username = serializers.CharField(source='assigned_by.username', read_only=True)

    class Meta:
        model = SurveyAssignment
        fields = '__all__'
        read_only_fields = ('assigned_at', 'assigned_by')

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_surveyor_name(self, obj):
        if obj.surveyor:
            return obj.surveyor.get_full_name() or obj.surveyor.username
        return None


class AssignSurveyorSerializer(serializers.Serializer):
    surveyor = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(role='SURVEYOR')
    )
    due_date = serializers.DateField(required=True)
    priority = serializers.ChoiceField(choices=Priority.choices, default=Priority.MEDIUM)
    instructions = serializers.CharField(required=False, allow_blank=True, default="")


class ReassignSurveyorSerializer(serializers.Serializer):
    surveyor = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(role='SURVEYOR')
    )
    due_date = serializers.DateField(required=True)
    priority = serializers.ChoiceField(choices=Priority.choices, default=Priority.MEDIUM)
    instructions = serializers.CharField(required=False, allow_blank=True, default="")
    remarks = serializers.CharField(required=False, allow_blank=True, default="")


class ClaimStatusActionSerializer(serializers.Serializer):
    remarks = serializers.CharField(required=False, allow_blank=True, default="")


class ClaimSerializer(serializers.ModelSerializer):
    survey_type_code = serializers.CharField(source='survey_type.code', read_only=True)
    survey_type_name = serializers.CharField(source='survey_type.name', read_only=True)
    insurer_name = serializers.CharField(source='insurer.company_name', read_only=True)
    insured_name = serializers.CharField(source='insured.name', read_only=True)
    assigned_surveyor_name = serializers.SerializerMethodField()
    assigned_surveyor_id = serializers.SerializerMethodField()

    class Meta:
        model = Claim
        fields = '__all__'
        read_only_fields = ('claim_number', 'created_at', 'updated_at', 'created_by')

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_assigned_surveyor_name(self, obj):
        surveyor = obj.current_surveyor
        if surveyor:
            return surveyor.get_full_name() or surveyor.username
        return None

    @extend_schema_field(serializers.IntegerField(allow_null=True))
    def get_assigned_surveyor_id(self, obj):
        surveyor = obj.current_surveyor
        return surveyor.id if surveyor else None


# Aliases for explicit semantic usage
ClaimListSerializer = ClaimSerializer
ClaimDetailSerializer = ClaimSerializer
