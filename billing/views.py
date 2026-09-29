"""
Billing DRF API Views — ServiceInvoice and ServiceInvoiceItem REST endpoints.

Provides JSON API for offline-capable invoice management with:
- Admin-only permission enforcement (superusers or role=ADMIN)
- DRAFT-only mutation locks on invoices and invoice items
- Optimistic concurrency control (base_updated_at and ETag/If-Match)
- Automatic financial recalculation on item mutations
"""

from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response

from config.concurrency import OptimisticConcurrencyMixin
from .models import ServiceInvoice, ServiceInvoiceItem
from .serializers import (
    ServiceInvoiceSerializer,
    ServiceInvoiceListSerializer,
    ServiceInvoiceItemSerializer,
)
from .services import (
    recalculate_invoice,
    mark_invoice_sent,
    record_invoice_payment,
    cancel_invoice,
    add_invoice_item,
    update_invoice_item,
    delete_invoice_item,
)


class IsAdmin(permissions.BasePermission):
    """Only admin users or superusers can access billing API."""
    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            (request.user.is_superuser or getattr(request.user, 'role', '') == 'ADMIN')
        )


class ServiceInvoiceViewSet(OptimisticConcurrencyMixin, viewsets.ModelViewSet):
    """
    CRUD API for ServiceInvoice.

    Endpoints:
      - GET /api/billing/invoices/          → list
      - GET /api/billing/invoices/{id}/     → detail
      - POST /api/billing/invoices/         → create
      - PUT/PATCH /api/billing/invoices/{id}/ → update (DRAFT only)
      - DELETE /api/billing/invoices/{id}/  → destroy (DRAFT only)

    Custom actions:
      - POST /api/billing/invoices/{id}/mark_sent/
      - POST /api/billing/invoices/{id}/record_payment/
      - POST /api/billing/invoices/{id}/cancel/
      - POST /api/billing/invoices/{id}/add_item/
    """
    permission_classes = [IsAdmin]
    queryset = ServiceInvoice.objects.select_related(
        'claim', 'claim__insured', 'created_by'
    ).prefetch_related('items').order_by('-created_at')

    def get_serializer_class(self):
        if self.action == 'list':
            return ServiceInvoiceListSerializer
        return ServiceInvoiceSerializer

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.status != ServiceInvoice.Status.DRAFT:
            return Response(
                {'detail': f"Cannot modify invoice #{instance.invoice_number}. Status is '{instance.status}' and locked."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.status != ServiceInvoice.Status.DRAFT:
            return Response(
                {'detail': f"Cannot modify invoice #{instance.invoice_number}. Status is '{instance.status}' and locked."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.status != ServiceInvoice.Status.DRAFT:
            return Response(
                {'detail': f"Cannot delete invoice #{instance.invoice_number}. Status is '{instance.status}' and locked."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=['post'])
    def mark_sent(self, request, pk=None):
        invoice = self.get_object()
        try:
            mark_invoice_sent(invoice, request.user)
            return Response(ServiceInvoiceSerializer(invoice).data)
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def record_payment(self, request, pk=None):
        invoice = self.get_object()
        payment_ref = request.data.get('payment_reference', '')
        try:
            record_invoice_payment(invoice, request.user, payment_ref)
            return Response(ServiceInvoiceSerializer(invoice).data)
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        invoice = self.get_object()
        reason = request.data.get('reason', '')
        try:
            cancel_invoice(invoice, request.user, reason)
            return Response(ServiceInvoiceSerializer(invoice).data)
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def add_item(self, request, pk=None):
        invoice = self.get_object()
        if invoice.status != ServiceInvoice.Status.DRAFT:
            return Response(
                {'detail': 'Can only add items to DRAFT invoices.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = ServiceInvoiceItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            item = add_invoice_item(
                invoice=invoice,
                description=serializer.validated_data['description'],
                quantity=serializer.validated_data.get('quantity', 1),
                rate=serializer.validated_data['rate'],
            )
            return Response(ServiceInvoiceItemSerializer(item).data, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class ServiceInvoiceItemViewSet(OptimisticConcurrencyMixin, viewsets.ModelViewSet):
    """
    CRUD API for ServiceInvoiceItem.
    Enforces Admin permission and DRAFT-only mutation lock on parent invoice.
    """
    permission_classes = [IsAdmin]
    serializer_class = ServiceInvoiceItemSerializer
    queryset = ServiceInvoiceItem.objects.select_related('invoice')

    def create(self, request, *args, **kwargs):
        invoice_id = request.data.get('invoice')
        if not invoice_id:
            return Response({'detail': 'invoice field is required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            invoice = ServiceInvoice.objects.get(pk=invoice_id)
        except ServiceInvoice.DoesNotExist:
            return Response({'detail': 'Invoice not found'}, status=status.HTTP_404_NOT_FOUND)

        if invoice.status != ServiceInvoice.Status.DRAFT:
            return Response(
                {'detail': f"Cannot add items. Invoice is '{invoice.status}' and locked."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = add_invoice_item(
            invoice=invoice,
            description=serializer.validated_data['description'],
            quantity=serializer.validated_data.get('quantity', 1),
            rate=serializer.validated_data['rate'],
        )
        return Response(self.get_serializer(item).data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        item = self.get_object()
        if item.invoice.status != ServiceInvoice.Status.DRAFT:
            return Response(
                {'detail': f"Cannot update item. Invoice is '{item.invoice.status}' and locked."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = self.get_serializer(item, data=request.data, partial=False)
        serializer.is_valid(raise_exception=True)
        updated = update_invoice_item(
            item=item,
            description=serializer.validated_data.get('description'),
            quantity=serializer.validated_data.get('quantity'),
            rate=serializer.validated_data.get('rate'),
        )
        return Response(self.get_serializer(updated).data)

    def partial_update(self, request, *args, **kwargs):
        item = self.get_object()
        if item.invoice.status != ServiceInvoice.Status.DRAFT:
            return Response(
                {'detail': f"Cannot update item. Invoice is '{item.invoice.status}' and locked."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = self.get_serializer(item, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated = update_invoice_item(
            item=item,
            description=serializer.validated_data.get('description'),
            quantity=serializer.validated_data.get('quantity'),
            rate=serializer.validated_data.get('rate'),
        )
        return Response(self.get_serializer(updated).data)

    def destroy(self, request, *args, **kwargs):
        item = self.get_object()
        if item.invoice.status != ServiceInvoice.Status.DRAFT:
            return Response(
                {'detail': f"Cannot delete item. Invoice is '{item.invoice.status}' and locked."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        delete_invoice_item(item)
        return Response(status=status.HTTP_204_NO_CONTENT)
