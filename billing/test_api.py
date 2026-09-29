from decimal import Decimal
from datetime import timedelta
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase, APIClient

from claims.models import Claim, ClaimStatus
from billing.models import ServiceInvoice, ServiceInvoiceItem
from billing.test_billing import BillingBaseTestCase


class BillingDRFAPITests(BillingBaseTestCase, APITestCase):
    def setUp(self):
        super().setUp()
        self.client = APIClient()

        # Create a sample draft invoice
        self.draft_invoice = ServiceInvoice.objects.create(
            claim=self.claim,
            invoice_date=timezone.localdate(),
            due_date=timezone.localdate() + timedelta(days=30),
            tax_percentage=Decimal('18.00'),
            created_by=self.admin,
        )
        self.draft_item = ServiceInvoiceItem.objects.create(
            invoice=self.draft_invoice,
            description='Preliminary Inspection Fee',
            quantity=Decimal('1.00'),
            rate=Decimal('10000.00'),
            amount=Decimal('10000.00'),
        )
        self.draft_invoice.subtotal = Decimal('10000.00')
        self.draft_invoice.tax_amount = Decimal('1800.00')
        self.draft_invoice.total_amount = Decimal('11800.00')
        self.draft_invoice.save()

    def test_admin_only_permission_enforcement(self):
        """Anonymous and surveyor users must be rejected; admin allowed."""
        # 1. Anonymous
        res = self.client.get('/api/billing/invoices/')
        self.assertIn(res.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])

        # 2. Surveyor
        self.client.force_authenticate(user=self.surveyor)
        res = self.client.get('/api/billing/invoices/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        res = self.client.get(f'/api/billing/invoices/{self.draft_invoice.id}/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        # 3. Admin
        self.client.force_authenticate(user=self.admin)
        res = self.client.get('/api/billing/invoices/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_draft_mutation_lock_on_invoices(self):
        """Sent/Paid/Cancelled invoices cannot be updated or deleted via API."""
        self.client.force_authenticate(user=self.admin)

        # Transition invoice to SENT
        res = self.client.post(f'/api/billing/invoices/{self.draft_invoice.id}/mark_sent/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.draft_invoice.refresh_from_db()
        self.assertEqual(self.draft_invoice.status, ServiceInvoice.Status.SENT)

        # Attempt PATCH
        res = self.client.patch(
            f'/api/billing/invoices/{self.draft_invoice.id}/',
            {'notes': 'Unauthorized update attempt'},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('locked', res.data['detail'].lower())

        # Attempt DELETE
        res = self.client.delete(f'/api/billing/invoices/{self.draft_invoice.id}/')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('locked', res.data['detail'].lower())

    def test_draft_mutation_lock_on_items(self):
        """Items cannot be added, updated, or deleted on non-DRAFT invoices."""
        self.client.force_authenticate(user=self.admin)

        # Mark sent
        self.client.post(f'/api/billing/invoices/{self.draft_invoice.id}/mark_sent/')

        # Try add item via /add_item/ action
        res = self.client.post(
            f'/api/billing/invoices/{self.draft_invoice.id}/add_item/',
            {'description': 'Late item', 'quantity': 1, 'rate': '1000.00'},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

        # Try add item via items viewset
        res = self.client.post(
            '/api/billing/items/',
            {'invoice': self.draft_invoice.id, 'description': 'Late item', 'quantity': 1, 'rate': '1000.00'},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

        # Try update existing item
        res = self.client.patch(
            f'/api/billing/items/{self.draft_item.id}/',
            {'rate': '20000.00'},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

        # Try delete existing item
        res = self.client.delete(f'/api/billing/items/{self.draft_item.id}/')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_optimistic_concurrency_base_updated_at(self):
        """Updating with a mismatched base_updated_at must return 409 Conflict."""
        self.client.force_authenticate(user=self.admin)

        # Capture base timestamp
        base_timestamp = self.draft_invoice.updated_at.isoformat()

        # Simulate another client updating the record in the meantime
        time_diff = timezone.now() + timedelta(minutes=5)
        ServiceInvoice.objects.filter(pk=self.draft_invoice.pk).update(updated_at=time_diff)

        # Send update with old base_updated_at
        res = self.client.patch(
            f'/api/billing/invoices/{self.draft_invoice.id}/',
            {'notes': 'Concurrent update attempt', 'base_updated_at': base_timestamp},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(res.data['code'], 'conflict')
        self.assertIn('Conflict', res.data['detail'])

    def test_optimistic_concurrency_if_match_header(self):
        """Updating with a mismatched If-Match ETag must return 409 Conflict."""
        self.client.force_authenticate(user=self.admin)

        res = self.client.patch(
            f'/api/billing/invoices/{self.draft_invoice.id}/',
            {'notes': 'ETag mismatch test'},
            HTTP_IF_MATCH='W/"bad_etag_12345"',
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(res.data['code'], 'conflict')

    def test_invoice_state_transitions(self):
        """Test mark_sent, record_payment, and cancel state transitions."""
        self.client.force_authenticate(user=self.admin)

        # 1. Mark sent
        res = self.client.post(f'/api/billing/invoices/{self.draft_invoice.id}/mark_sent/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['status'], ServiceInvoice.Status.SENT)

        # 2. Record payment
        res = self.client.post(
            f'/api/billing/invoices/{self.draft_invoice.id}/record_payment/',
            {'payment_reference': 'NEFT/UTR/88776655'},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['status'], ServiceInvoice.Status.PAID)
        self.assertEqual(res.data['payment_reference'], 'NEFT/UTR/88776655')
