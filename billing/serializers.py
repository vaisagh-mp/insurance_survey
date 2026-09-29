"""
Billing DRF Serializers — ServiceInvoice & ServiceInvoiceItem.

Provides JSON API for offline-capable invoice management.
"""

from rest_framework import serializers
from .models import ServiceInvoice, ServiceInvoiceItem


class ServiceInvoiceItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceInvoiceItem
        fields = ('id', 'description', 'quantity', 'rate', 'amount')
        read_only_fields = ('id', 'amount')


class ServiceInvoiceSerializer(serializers.ModelSerializer):
    items = ServiceInvoiceItemSerializer(many=True, read_only=True)
    claim_number = serializers.CharField(source='claim.claim_number', read_only=True)
    insured_name = serializers.CharField(source='claim.insured.name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)

    class Meta:
        model = ServiceInvoice
        fields = (
            'id', 'invoice_number', 'claim', 'claim_number', 'insured_name',
            'invoice_date', 'due_date', 'status',
            'subtotal', 'tax_percentage', 'tax_amount', 'total_amount',
            'notes', 'remarks',
            'sent_at', 'paid_at', 'payment_reference',
            'created_by', 'created_by_name',
            'created_at', 'updated_at',
            'items',
        )
        read_only_fields = (
            'id', 'invoice_number', 'subtotal', 'tax_amount', 'total_amount',
            'sent_at', 'paid_at',
            'created_by', 'created_by_name',
            'created_at', 'updated_at',
        )


class ServiceInvoiceListSerializer(serializers.ModelSerializer):
    """Lighter serializer for list views (no nested items)."""
    claim_number = serializers.CharField(source='claim.claim_number', read_only=True)
    insured_name = serializers.CharField(source='claim.insured.name', read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)

    class Meta:
        model = ServiceInvoice
        fields = (
            'id', 'invoice_number', 'claim', 'claim_number', 'insured_name',
            'invoice_date', 'due_date', 'status', 'is_overdue',
            'total_amount', 'created_at', 'updated_at',
        )
        read_only_fields = fields
