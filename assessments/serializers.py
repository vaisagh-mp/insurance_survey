from decimal import Decimal
from rest_framework import serializers
from .models import Invoice, Assessment, AssessmentItem
from .services import recalculate_assessment


class InvoiceSerializer(serializers.ModelSerializer):
    claim_number = serializers.CharField(source='claim.claim_number', read_only=True)
    verified_by_username = serializers.CharField(source='verified_by.username', read_only=True)

    class Meta:
        model = Invoice
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at', 'verified_by')


class AssessmentItemSerializer(serializers.ModelSerializer):
    assessed_amount = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)

    class Meta:
        model = AssessmentItem
        fields = '__all__'
        extra_kwargs = {
            'assessment': {'required': False}
        }


class AssessmentSerializer(serializers.ModelSerializer):
    claim_number = serializers.CharField(source='claim.claim_number', read_only=True)
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)
    items = AssessmentItemSerializer(many=True, required=False)

    class Meta:
        model = Assessment
        fields = '__all__'
        read_only_fields = (
            'gross_assessed_loss',
            'underinsurance_amount',
            'adjusted_loss',
            'net_assessed_loss',
            'created_by',
            'created_at',
            'updated_at'
        )
        extra_kwargs = {
            'claim': {'required': False},
            'created_by': {'required': False},
        }

    def create(self, validated_data):
        items_data = validated_data.pop('items', [])
        assessment = Assessment.objects.create(**validated_data)
        for item_data in items_data:
            item_data.pop('assessment', None)
            AssessmentItem.objects.create(assessment=assessment, **item_data)
        recalculate_assessment(assessment)
        assessment.refresh_from_db()
        return assessment

    def update(self, instance, validated_data):
        items_data = validated_data.pop('items', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if items_data is not None:
            instance.items.all().delete()
            for item_data in items_data:
                item_data.pop('assessment', None)
                AssessmentItem.objects.create(assessment=instance, **item_data)

        recalculate_assessment(instance)
        instance.refresh_from_db()
        return instance
