from decimal import Decimal
from datetime import date, timedelta
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError, PermissionDenied
from django.utils import timezone

from claims.models import Insurer, Insured, Policy, Claim, ClaimStatus
from surveys.models import SurveyType
from billing.models import ServiceInvoice, ServiceInvoiceItem
from billing.services import (
    recalculate_invoice,
    mark_invoice_sent,
    record_invoice_payment,
    cancel_invoice,
    generate_invoice_pdf,
    add_invoice_item,
    update_invoice_item,
    delete_invoice_item,
)

User = get_user_model()


class BillingBaseTestCase(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='admin_billing',
            email='admin@billing.com',
            password='password123',
            role=User.Role.ADMIN
        )
        self.surveyor = User.objects.create_user(
            username='surveyor_billing',
            email='surveyor@billing.com',
            password='password123',
            role=User.Role.SURVEYOR
        )

        self.insurer = Insurer.objects.create(
            company_name='National Insurance Co',
            branch_name='Mumbai Central',
            address='123 Marine Drive',
            city='Mumbai',
            state='Maharashtra',
            pincode='400001',
            contact_person='Mr. Mehta',
            phone='9876543210',
            email='mehta@national.com',
            gstin='27AAACN0000A1Z1'
        )
        self.insured = Insured.objects.create(
            name='Acme Logistics Pvt Ltd',
            address='Plot 4, MIDC',
            city='Navi Mumbai',
            state='Maharashtra',
            pincode='400705',
            contact_person='Rajesh Kumar',
            phone='9876543211',
            email='rajesh@acme.com'
        )
        self.survey_type = SurveyType.objects.create(
            name='Engineering Survey',
            code='ENG-01'
        )
        self.policy = Policy.objects.create(
            policy_number='POL-ENG-9988',
            policy_type='Machinery Breakdown',
            insurer=self.insurer,
            start_datetime=timezone.now() - timedelta(days=60),
            end_datetime=timezone.now() + timedelta(days=300),
            sum_insured=Decimal('5000000.00'),
            excess=Decimal('50000.00'),
            commodity='Industrial Machinery',
            subject_matter='Steam Turbine 5MW'
        )
        self.claim = Claim.objects.create(
            survey_type=self.survey_type,
            insurer=self.insurer,
            insured=self.insured,
            policy=self.policy,
            instruction_date=timezone.localdate() - timedelta(days=10),
            instruction_source='Email Instruction',
            date_of_loss=timezone.localdate() - timedelta(days=12),
            nature_of_loss='Turbine Failure',
            loss_location='Turbine Room 1, Acme Plant',
            status=ClaimStatus.INSPECTION_COMPLETED,
            created_by=self.admin
        )


class ServiceInvoiceCalculationTests(BillingBaseTestCase):
    def test_recalculate_invoice_worked_example(self):
        """
        Worked example:
        2 items: qty 1 rate 15000, qty 1 rate 5000. Tax: 18%.
        subtotal = 20000.00, tax_amount = 3600.00, total_amount = 23600.00.
        """
        invoice = ServiceInvoice.objects.create(
            claim=self.claim,
            invoice_date=timezone.localdate(),
            due_date=timezone.localdate() + timedelta(days=30),
            tax_percentage=Decimal('18.00'),
            created_by=self.admin
        )
        ServiceInvoiceItem.objects.create(
            invoice=invoice,
            description='Preliminary Survey Fee',
            quantity=Decimal('1.00'),
            rate=Decimal('15000.00')
        )
        ServiceInvoiceItem.objects.create(
            invoice=invoice,
            description='Conveyance & Out of Pocket',
            quantity=Decimal('1.00'),
            rate=Decimal('5000.00')
        )

        recalculate_invoice(invoice)
        invoice.refresh_from_db()

        self.assertEqual(invoice.subtotal, Decimal('20000.00'))
        self.assertEqual(invoice.tax_amount, Decimal('3600.00'))
        self.assertEqual(invoice.total_amount, Decimal('23600.00'))

    def test_auto_recalculate_on_item_add_and_delete(self):
        """
        Fix 2: Subtotal/tax/total are updated immediately upon item addition and deletion
        without needing a separate save call.
        """
        invoice = ServiceInvoice.objects.create(
            claim=self.claim,
            invoice_date=timezone.localdate(),
            due_date=timezone.localdate() + timedelta(days=30),
            tax_percentage=Decimal('18.00'),
            created_by=self.admin
        )

        # 1. Add item 1
        item1 = add_invoice_item(invoice, 'Inspection Fee', quantity=Decimal('1.00'), rate=Decimal('10000.00'))
        invoice.refresh_from_db()
        self.assertEqual(invoice.subtotal, Decimal('10000.00'))
        self.assertEqual(invoice.tax_amount, Decimal('1800.00'))
        self.assertEqual(invoice.total_amount, Decimal('11800.00'))

        # 2. Add item 2
        item2 = add_invoice_item(invoice, 'Photo Charges', quantity=Decimal('2.00'), rate=Decimal('1500.00'))
        invoice.refresh_from_db()
        self.assertEqual(invoice.subtotal, Decimal('13000.00'))
        self.assertEqual(invoice.tax_amount, Decimal('2340.00'))
        self.assertEqual(invoice.total_amount, Decimal('15340.00'))

        # 3. Delete item 1
        delete_invoice_item(item1)
        invoice.refresh_from_db()
        self.assertEqual(invoice.subtotal, Decimal('3000.00'))
        self.assertEqual(invoice.tax_amount, Decimal('540.00'))
        self.assertEqual(invoice.total_amount, Decimal('3540.00'))


class ServiceInvoiceNumberAndUniquenessTests(BillingBaseTestCase):
    def test_invoice_number_auto_generation_sequence(self):
        """Auto-generated invoice_number follows SINV-00001, SINV-00002 etc."""
        inv1 = ServiceInvoice.objects.create(
            claim=self.claim,
            invoice_date=timezone.localdate(),
            due_date=timezone.localdate() + timedelta(days=30),
            created_by=self.admin
        )
        self.assertTrue(inv1.invoice_number.startswith('SINV-'))

        # Create another claim for inv2
        claim2 = Claim.objects.create(
            survey_type=self.survey_type,
            insurer=self.insurer,
            insured=self.insured,
            policy=self.policy,
            instruction_date=timezone.localdate(),
            instruction_source='Email',
            date_of_loss=timezone.localdate(),
            nature_of_loss='Fire',
            loss_location='Factory',
            created_by=self.admin
        )
        inv2 = ServiceInvoice.objects.create(
            claim=claim2,
            invoice_date=timezone.localdate(),
            due_date=timezone.localdate() + timedelta(days=30),
            created_by=self.admin
        )
        self.assertNotEqual(inv1.invoice_number, inv2.invoice_number)
        num1 = int(inv1.invoice_number.split('-')[1])
        num2 = int(inv2.invoice_number.split('-')[1])
        self.assertEqual(num2, num1 + 1)

    def test_duplicate_active_invoice_rejected_on_same_claim(self):
        """Cannot create a second non-cancelled invoice on the same claim."""
        ServiceInvoice.objects.create(
            claim=self.claim,
            invoice_date=timezone.localdate(),
            due_date=timezone.localdate() + timedelta(days=30),
            created_by=self.admin
        )
        duplicate = ServiceInvoice(
            claim=self.claim,
            invoice_date=timezone.localdate(),
            due_date=timezone.localdate() + timedelta(days=30),
            created_by=self.admin
        )
        with self.assertRaises(ValidationError):
            duplicate.full_clean()

    def test_create_new_invoice_after_cancellation_succeeds(self):
        """After cancelling an invoice on a claim, creating a new one succeeds."""
        inv1 = ServiceInvoice.objects.create(
            claim=self.claim,
            invoice_date=timezone.localdate(),
            due_date=timezone.localdate() + timedelta(days=30),
            created_by=self.admin
        )
        cancel_invoice(inv1, self.admin, reason="Initial invoice details were erroneous")
        inv1.refresh_from_db()
        self.assertEqual(inv1.status, ServiceInvoice.Status.CANCELLED)

        # Creating new invoice on same claim must now succeed
        inv2 = ServiceInvoice(
            claim=self.claim,
            invoice_date=timezone.localdate(),
            due_date=timezone.localdate() + timedelta(days=30),
            created_by=self.admin
        )
        inv2.full_clean()
        inv2.save()
        self.assertEqual(inv2.status, ServiceInvoice.Status.DRAFT)


class ServiceInvoiceStateTransitionTests(BillingBaseTestCase):
    def setUp(self):
        super().setUp()
        self.invoice = ServiceInvoice.objects.create(
            claim=self.claim,
            invoice_date=timezone.localdate(),
            due_date=timezone.localdate() + timedelta(days=30),
            created_by=self.admin
        )

    def test_draft_to_sent_success(self):
        mark_invoice_sent(self.invoice, self.admin)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, ServiceInvoice.Status.SENT)
        self.assertIsNotNone(self.invoice.sent_at)

    def test_sent_to_sent_fails(self):
        mark_invoice_sent(self.invoice, self.admin)
        with self.assertRaises(ValidationError):
            mark_invoice_sent(self.invoice, self.admin)

    def test_draft_to_paid_fails(self):
        with self.assertRaises(ValidationError):
            record_invoice_payment(self.invoice, self.admin, payment_reference="REF-001")

    def test_sent_to_paid_success(self):
        mark_invoice_sent(self.invoice, self.admin)
        record_invoice_payment(self.invoice, self.admin, payment_reference="NEFT-998877")
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, ServiceInvoice.Status.PAID)
        self.assertIsNotNone(self.invoice.paid_at)
        self.assertEqual(self.invoice.payment_reference, "NEFT-998877")

    def test_draft_to_cancelled_success(self):
        cancel_invoice(self.invoice, self.admin, reason="Survey scope revoked")
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, ServiceInvoice.Status.CANCELLED)

    def test_sent_to_cancelled_success(self):
        mark_invoice_sent(self.invoice, self.admin)
        cancel_invoice(self.invoice, self.admin, reason="Insurer requested credit note and rebill")
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, ServiceInvoice.Status.CANCELLED)

    def test_paid_to_cancelled_fails(self):
        mark_invoice_sent(self.invoice, self.admin)
        record_invoice_payment(self.invoice, self.admin, payment_reference="REF-001")
        with self.assertRaises(ValidationError):
            cancel_invoice(self.invoice, self.admin, reason="Attempt to cancel paid invoice")

    def test_cancel_requires_non_blank_reason(self):
        with self.assertRaises(ValidationError):
            cancel_invoice(self.invoice, self.admin, reason="")
        with self.assertRaises(ValidationError):
            cancel_invoice(self.invoice, self.admin, reason="   ")

    def test_cancel_appends_reason_to_remarks(self):
        """Fix 3: Cancellation reason must be appended to remarks, preserving existing remarks."""
        self.invoice.remarks = "Initial internal surveyor billing note."
        self.invoice.save()

        cancel_invoice(self.invoice, self.admin, reason="Claim withdrawn by insurer.")
        self.invoice.refresh_from_db()

        self.assertIn("Initial internal surveyor billing note.", self.invoice.remarks)
        self.assertIn("Cancelled by", self.invoice.remarks)
        self.assertIn("Claim withdrawn by insurer.", self.invoice.remarks)


class ServiceInvoiceItemImmutabilityTests(BillingBaseTestCase):
    """
    Fix 1: Lock line-item edits once an invoice leaves DRAFT.
    claim_billing_item_add, claim_billing_item_edit, claim_billing_item_delete,
    and claim_billing_save must reject changes when not DRAFT.
    """
    def setUp(self):
        super().setUp()
        self.client = Client()
        self.client.force_login(self.admin)
        self.invoice = ServiceInvoice.objects.create(
            claim=self.claim,
            invoice_date=timezone.localdate(),
            due_date=timezone.localdate() + timedelta(days=30),
            created_by=self.admin
        )
        self.item = add_invoice_item(self.invoice, 'Survey Fee', Decimal('1.00'), Decimal('10000.00'))

    def test_service_layer_rejects_item_mutations_when_sent(self):
        mark_invoice_sent(self.invoice, self.admin)

        with self.assertRaises(ValidationError):
            add_invoice_item(self.invoice, 'Extra Fee', Decimal('1.00'), Decimal('2000.00'))

        with self.assertRaises(ValidationError):
            update_invoice_item(self.item, rate=Decimal('15000.00'))

        with self.assertRaises(ValidationError):
            delete_invoice_item(self.item)

    def test_endpoint_rejects_item_add_when_not_draft(self):
        mark_invoice_sent(self.invoice, self.admin)
        url = f"/claims/{self.claim.id}/billing/item/add/"
        response = self.client.post(url, {
            'description': 'Attempted Item',
            'quantity': '1',
            'rate': '5000'
        })
        self.assertEqual(response.status_code, 400)
        # Verify item was not created
        self.assertEqual(self.invoice.items.count(), 1)

    def test_endpoint_rejects_item_edit_when_not_draft(self):
        mark_invoice_sent(self.invoice, self.admin)
        url = f"/claims/{self.claim.id}/billing/item/{self.item.id}/edit/"
        response = self.client.post(url, {
            'description': 'Modified Description',
            'quantity': '2',
            'rate': '20000'
        })
        self.assertEqual(response.status_code, 400)
        self.item.refresh_from_db()
        self.assertEqual(self.item.rate, Decimal('10000.00'))

    def test_endpoint_rejects_item_delete_when_not_draft(self):
        mark_invoice_sent(self.invoice, self.admin)
        url = f"/claims/{self.claim.id}/billing/item/{self.item.id}/delete/"
        response = self.client.post(url)
        self.assertEqual(response.status_code, 400)
        self.assertTrue(ServiceInvoiceItem.objects.filter(id=self.item.id).exists())

    def test_endpoint_rejects_header_save_when_not_draft(self):
        mark_invoice_sent(self.invoice, self.admin)
        url = f"/claims/{self.claim.id}/billing/save/"
        response = self.client.post(url, {
            'tax_percentage': '5.00'
        })
        self.assertEqual(response.status_code, 400)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.tax_percentage, Decimal('18.00'))


class ServiceInvoicePropertyTests(BillingBaseTestCase):
    def test_is_overdue_property(self):
        today = timezone.localdate()

        # 1. SENT and past due date -> Overdue
        inv_sent_past = ServiceInvoice.objects.create(
            claim=self.claim,
            invoice_date=today - timedelta(days=40),
            due_date=today - timedelta(days=10),
            status=ServiceInvoice.Status.SENT,
            created_by=self.admin
        )
        self.assertTrue(inv_sent_past.is_overdue)

        # 2. SENT and future due date -> Not overdue
        inv_sent_future = ServiceInvoice(
            due_date=today + timedelta(days=10),
            status=ServiceInvoice.Status.SENT
        )
        self.assertFalse(inv_sent_future.is_overdue)

        # 3. DRAFT and past due date -> Not overdue (drafts can't be overdue)
        inv_draft_past = ServiceInvoice(
            due_date=today - timedelta(days=10),
            status=ServiceInvoice.Status.DRAFT
        )
        self.assertFalse(inv_draft_past.is_overdue)

        # 4. PAID and past due date -> Not overdue (already settled)
        inv_paid_past = ServiceInvoice(
            due_date=today - timedelta(days=10),
            status=ServiceInvoice.Status.PAID
        )
        self.assertFalse(inv_paid_past.is_overdue)


class ServiceInvoicePDFGenerationTests(BillingBaseTestCase):
    def test_generate_invoice_pdf_creates_valid_pdf_with_items_and_firm_details(self):
        invoice = ServiceInvoice.objects.create(
            claim=self.claim,
            invoice_date=timezone.localdate(),
            due_date=timezone.localdate() + timedelta(days=30),
            tax_percentage=Decimal('18.00'),
            notes="Bank: HDFC Bank\nA/C: 1122334455\nIFSC: HDFC0000123",
            remarks="Confidential partner review note",
            created_by=self.admin
        )
        add_invoice_item(invoice, 'Survey & Loss Assessment', Decimal('1.00'), Decimal('25000.00'))
        add_invoice_item(invoice, 'Travel & Mileage', Decimal('1.00'), Decimal('3500.00'))

        pdf_bytes = generate_invoice_pdf(invoice)
        self.assertIsInstance(pdf_bytes, bytes)
        self.assertTrue(pdf_bytes.startswith(b'%PDF'))
        self.assertGreater(len(pdf_bytes), 1000)


class ServiceInvoiceAccessControlTests(BillingBaseTestCase):
    def setUp(self):
        super().setUp()
        self.client = Client()
        self.invoice = ServiceInvoice.objects.create(
            claim=self.claim,
            invoice_date=timezone.localdate(),
            due_date=timezone.localdate() + timedelta(days=30),
            created_by=self.admin
        )

    def test_surveyor_denied_on_billing_views(self):
        """Surveyor must be denied (403 PermissionDenied) on all billing views."""
        self.client.force_login(self.surveyor)

        endpoints = [
            ('/billing/', 'get'),
            (f'/claims/{self.claim.id}/billing/create/', 'post'),
            (f'/claims/{self.claim.id}/billing/save/', 'post'),
            (f'/claims/{self.claim.id}/billing/item/add/', 'post'),
            (f'/claims/{self.claim.id}/billing/mark-sent/', 'post'),
            (f'/claims/{self.claim.id}/billing/record-payment/', 'post'),
            (f'/claims/{self.claim.id}/billing/cancel/', 'post'),
            (f'/claims/{self.claim.id}/billing/pdf/', 'get'),
        ]

        for url, method in endpoints:
            if method == 'get':
                resp = self.client.get(url)
            else:
                resp = self.client.post(url, {})
            self.assertEqual(
                resp.status_code, 403,
                f"Surveyor was not denied (expected 403) on {method.upper()} {url}, got {resp.status_code}"
            )

    def test_admin_allowed_on_billing_views(self):
        """Admin is allowed on billing views."""
        self.client.force_login(self.admin)

        resp = self.client.get('/billing/')
        self.assertEqual(resp.status_code, 200)

        resp = self.client.get(f'/claims/{self.claim.id}/billing/pdf/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/pdf')

    def test_unauthenticated_redirected_to_login(self):
        """Unauthenticated user redirected to login."""
        resp = self.client.get('/billing/')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login/', resp.url)


class FirmGSTINSystemCheckTests(TestCase):
    """Tests for the Django system check that validates FIRM_GSTIN in production."""

    def test_warning_emitted_when_debug_false_and_placeholder_gstin(self):
        from django.test import override_settings
        from billing.apps import check_firm_gstin_production

        with override_settings(DEBUG=False, FIRM_GSTIN='27AAACS0000A1Z5'):
            warnings = check_firm_gstin_production(None)
            self.assertEqual(len(warnings), 1)
            self.assertEqual(warnings[0].id, 'billing.W001')
            self.assertIn("FIRM_GSTIN", warnings[0].msg)

    def test_no_warning_when_debug_false_and_custom_gstin(self):
        from django.test import override_settings
        from billing.apps import check_firm_gstin_production

        with override_settings(DEBUG=False, FIRM_GSTIN='27ABCDE1234F1Z5'):
            warnings = check_firm_gstin_production(None)
            self.assertEqual(len(warnings), 0)

    def test_no_warning_when_debug_true_with_placeholder(self):
        from django.test import override_settings
        from billing.apps import check_firm_gstin_production

        with override_settings(DEBUG=True, FIRM_GSTIN='27AAACS0000A1Z5'):
            warnings = check_firm_gstin_production(None)
            self.assertEqual(len(warnings), 0)
