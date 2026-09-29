"""
Billing API URL Configuration.

Registers the DRF router for ServiceInvoice and ServiceInvoiceItem
API endpoints under /api/billing/.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ServiceInvoiceViewSet, ServiceInvoiceItemViewSet

router = DefaultRouter()
router.register('invoices', ServiceInvoiceViewSet, basename='billing-invoice')
router.register('items', ServiceInvoiceItemViewSet, basename='billing-item')

app_name = 'billing-api'

urlpatterns = [
    path('', include(router.urls)),
]
