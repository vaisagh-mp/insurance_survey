from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import SurveyType, Inspection, InspectionPhoto, InspectionObservation

User = get_user_model()


class SurveyTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = SurveyType
        fields = '__all__'


class InspectionPhotoSerializer(serializers.ModelSerializer):
    uploaded_by_username = serializers.CharField(source='uploaded_by.username', read_only=True)

    class Meta:
        model = InspectionPhoto
        fields = '__all__'
        read_only_fields = ('uploaded_by', 'created_at')


class InspectionObservationSerializer(serializers.ModelSerializer):
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)

    class Meta:
        model = InspectionObservation
        fields = '__all__'
        read_only_fields = ('created_by', 'created_at')


class InspectionSerializer(serializers.ModelSerializer):
    claim_number = serializers.CharField(source='claim.claim_number', read_only=True)
    surveyor_name = serializers.SerializerMethodField()
    photos = InspectionPhotoSerializer(many=True, read_only=True)
    observations_list = InspectionObservationSerializer(many=True, read_only=True)

    class Meta:
        model = Inspection
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')
        extra_kwargs = {
            'claim': {'required': False},
            'surveyor': {'required': False}
        }

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_surveyor_name(self, obj):
        if obj.surveyor:
            return obj.surveyor.get_full_name() or obj.surveyor.username
        return None
