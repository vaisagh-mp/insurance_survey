from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from .models import ILA, ISR, FSR


class ILASerializer(serializers.ModelSerializer):
    claim_number = serializers.CharField(source='claim.claim_number', read_only=True)
    prepared_by_username = serializers.CharField(source='prepared_by.username', read_only=True)
    surveyor_name = serializers.SerializerMethodField()

    class Meta:
        model = ILA
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at', 'prepared_by')
        extra_kwargs = {
            'claim': {'required': False},
            'prepared_by': {'required': False},
            'surveyor': {'required': False},
        }

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_surveyor_name(self, obj):
        if obj.surveyor:
            return obj.surveyor.get_full_name() or obj.surveyor.username
        return None


class ISRSerializer(serializers.ModelSerializer):
    claim_number = serializers.CharField(source='claim.claim_number', read_only=True)
    prepared_by_username = serializers.CharField(source='prepared_by.username', read_only=True)

    class Meta:
        model = ISR
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at', 'prepared_by')
        extra_kwargs = {
            'claim': {'required': False},
            'prepared_by': {'required': False},
        }


class FSRSerializer(serializers.ModelSerializer):
    claim_number = serializers.CharField(source='claim.claim_number', read_only=True)
    prepared_by_username = serializers.CharField(source='prepared_by.username', read_only=True)
    disclaimer_note = serializers.CharField(default=FSR.DISCLAIMER_NOTE, read_only=True)
    gross_assessed_loss = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)
    net_assessed_loss = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)

    class Meta:
        model = FSR
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at', 'prepared_by')
        extra_kwargs = {
            'claim': {'required': False},
            'prepared_by': {'required': False},
        }
