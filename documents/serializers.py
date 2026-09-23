from rest_framework import serializers
from .models import DocumentType, ClaimDocument, Requirement


class DocumentTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentType
        fields = '__all__'


class ClaimDocumentSerializer(serializers.ModelSerializer):
    document_type_name = serializers.CharField(source='document_type.name', read_only=True)
    uploaded_by_username = serializers.CharField(source='uploaded_by.username', read_only=True)
    verified_by_username = serializers.CharField(source='verified_by.username', read_only=True)
    claim_number = serializers.CharField(source='claim.claim_number', read_only=True)

    class Meta:
        model = ClaimDocument
        fields = '__all__'
        read_only_fields = ('uploaded_by', 'uploaded_at', 'verified_by', 'verified_at')
        extra_kwargs = {
            'claim': {'required': False},
            'uploaded_by': {'required': False},
        }


class RequirementSerializer(serializers.ModelSerializer):
    claim_number = serializers.CharField(source='claim.claim_number', read_only=True)
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)

    class Meta:
        model = Requirement
        fields = '__all__'
        read_only_fields = ('created_by', 'created_at', 'updated_at')
        extra_kwargs = {
            'claim': {'required': False},
            'created_by': {'required': False},
        }
