from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from .models import User, SurveyorProfile


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Custom TokenObtainPair serializer returning tokens and user info."""

    def validate(self, attrs):
        data = super().validate(attrs)
        data['user'] = {
            'id': self.user.id,
            'username': self.user.username,
            'email': self.user.email,
            'role': self.user.role,
            'first_name': self.user.first_name,
            'last_name': self.user.last_name,
        }
        return data


class SurveyorProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = SurveyorProfile
        fields = (
            'license_number',
            'license_expiry',
            'phone',
            'address',
            'specialization',
            'created_at',
            'updated_at',
        )


class UserMeSerializer(serializers.ModelSerializer):
    surveyor_profile = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            'id',
            'username',
            'email',
            'first_name',
            'last_name',
            'role',
            'surveyor_profile',
        )

    @extend_schema_field(SurveyorProfileSerializer)
    def get_surveyor_profile(self, obj):
        if obj.is_surveyor_role and hasattr(obj, 'surveyor_profile'):
            return SurveyorProfileSerializer(obj.surveyor_profile).data
        return None


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField(required=True)
