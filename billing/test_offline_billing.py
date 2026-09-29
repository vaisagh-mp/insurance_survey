import json
from datetime import date, timedelta
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.utils import timezone

from claims.models import Claim, ClaimStatus, Insurer, Insured, Policy
from surveys.models import SurveyType
from billing.models import ServiceInvoice, ServiceInvoiceItem

User = get_user_model()


class OfflineBillingTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin_user = User.objects.create_user(
            username='admin_billing_rollout',
            email='admin@billing.test',
            password='password123',
            role=User.Role.ADMIN
        )
        self.surveyor_user = User.objects.create_user(
            username='surveyor_billing_rollout',
            email='surveyor@billing.test',
            password='password123',
            role=User.Role.SURVEYOR
        )

        self.survey_type = SurveyType.objects.get(code='FIRE')
        self.insurer = Insurer.objects.create(
            company_name='Billing Insurer Co',
            branch_name='Downtown',
            address='100 Main St',
            city='Metro City',
            state='State',
            pincode='400001',
            contact_person='John Doe',
            phone='555-0202',
            email='claims@billing.test'
        )
        self.insured = Insured.objects.create(
            name='Billing Insured Party',
            company_name='Billing Corp',
            address='Plot 5 Industrial Estate',
            city='Metro City',
            state='State',
            pincode='400002',
            phone='555-0303',
            email='info@billingcorp.test',
            contact_person='Jane Smith'
        )
        now = timezone.now()
        self.policy = Policy.objects.create(
            insurer=self.insurer,
            policy_number='POL-BILL-ROLLOUT-001',
            policy_type='Fire Policy',
            start_datetime=now,
            end_datetime=now + timedelta(days=365),
            sum_insured=Decimal('5000000.00'),
            excess=Decimal('10000.00'),
            commodity='Plant & Machinery',
            subject_matter='Factory Building'
        )

        self.claim = Claim.objects.create(
            survey_type=self.survey_type,
            insurer=self.insurer,
            insured=self.insured,
            policy=self.policy,
            instruction_date=date(2026, 9, 1),
            instruction_source='Email',
            date_of_loss=date(2026, 8, 30),
            nature_of_loss='Fire Damage',
            loss_location='Unit 1 Factory',
            claimed_amount=Decimal('40000.00'),
            status=ClaimStatus.ASSIGNED,
            created_by=self.admin_user
        )

    # ==========================================
    # AREA 7: BILLING
    # ==========================================
    def test_claim_billing_create_html_and_json(self):
        """Dual-accept claim_billing_create."""
        self.client.force_login(self.admin_user)

        # JSON success
        resp_json = self.client.post(
            f'/claims/{self.claim.id}/billing/create/',
            data=json.dumps({
                'invoice_date': '2026-09-10',
                'due_date': '2026-09-25',
                'tax_percentage': '18.00',
                'notes': 'Payment via bank transfer'
            }),
            content_type='application/json',
            HTTP_ACCEPT='application/json'
        )
        self.assertEqual(resp_json.status_code, 201)
        res_data = resp_json.json()
        self.assertEqual(res_data['status'], 'success')
        self.assertIn('id', res_data)

        # Cancel it so another can be tested
        inv = ServiceInvoice.objects.get(id=res_data['id'])
        inv.status = ServiceInvoice.Status.CANCELLED
        inv.save()

        # HTML path
        resp_html = self.client.post(
            f'/claims/{self.claim.id}/billing/create/',
            data={
                'invoice_date': '2026-09-11',
                'due_date': '2026-09-26',
                'tax_percentage': '18.00'
            }
        )
        self.assertEqual(resp_html.status_code, 302)

    def test_claim_billing_save_draft_lock_and_conflict(self):
        """Rule 2 fix: DRAFT lock rejection returns JSON 400 with code='locked',
        and stale base_updated_at returns 409."""
        self.client.force_login(self.admin_user)
        inv = ServiceInvoice.objects.create(
            claim=self.claim,
            due_date=date(2026, 9, 30),
            created_by=self.admin_user
        )

        # 1. Success on DRAFT invoice
        resp_ok = self.client.post(
            f'/claims/{self.claim.id}/billing/save/',
            data=json.dumps({
                'invoice_date': '2026-09-15',
                'due_date': '2026-10-05',
                'tax_percentage': '18.00',
                'notes': 'Updated notes',
                'base_updated_at': inv.updated_at.isoformat()
            }),
            content_type='application/json',
            HTTP_ACCEPT='application/json'
        )
        self.assertEqual(resp_ok.status_code, 200)

        # 2. Concurrency conflict on DRAFT invoice
        stale_ts = (inv.updated_at - timedelta(hours=1)).isoformat()
        resp_conf = self.client.post(
            f'/claims/{self.claim.id}/billing/save/',
            data=json.dumps({
                'due_date': '2026-10-10',
                'base_updated_at': stale_ts
            }),
            content_type='application/json',
            HTTP_ACCEPT='application/json'
        )
        self.assertEqual(resp_conf.status_code, 409)

        # 3. Lock rejection when SENT (Rule 2 fix)
        inv.status = ServiceInvoice.Status.SENT
        inv.save()

        resp_locked = self.client.post(
            f'/claims/{self.claim.id}/billing/save/',
            data=json.dumps({
                'due_date': '2026-10-15',
                'base_updated_at': inv.updated_at.isoformat()
            }),
            content_type='application/json',
            HTTP_ACCEPT='application/json'
        )
        self.assertEqual(resp_locked.status_code, 400)
        res_lock_data = resp_locked.json()
        self.assertEqual(res_lock_data.get('code'), 'locked')
        self.assertIn('Only DRAFT invoices can be edited', res_lock_data.get('detail', ''))

    def test_claim_billing_item_add_edit_draft_lock(self):
        """Rule 2 fix: item add/edit locked when not DRAFT."""
        self.client.force_login(self.admin_user)
        inv = ServiceInvoice.objects.create(
            claim=self.claim,
            due_date=date(2026, 9, 30),
            created_by=self.admin_user
        )

        # 1. Add item success
        resp_add = self.client.post(
            f'/claims/{self.claim.id}/billing/item/add/',
            data=json.dumps({
                'description': 'Survey fee',
                'quantity': '1.00',
                'rate': '15000.00'
            }),
            content_type='application/json',
            HTTP_ACCEPT='application/json'
        )
        self.assertEqual(resp_add.status_code, 201)
        item_id = resp_add.json()['id']

        # 2. Edit item success
        item = ServiceInvoiceItem.objects.get(id=item_id)
        resp_edit = self.client.post(
            f'/claims/{self.claim.id}/billing/item/{item.id}/edit/',
            data=json.dumps({
                'description': 'Survey fee modified',
                'quantity': '1.00',
                'rate': '16000.00',
                'base_updated_at': item.updated_at.isoformat()
            }),
            content_type='application/json',
            HTTP_ACCEPT='application/json'
        )
        self.assertEqual(resp_edit.status_code, 200)

        # 3. Mark invoice SENT, test lock rejections on add and edit
        inv.status = ServiceInvoice.Status.SENT
        inv.save()

        # Add locked
        resp_add_locked = self.client.post(
            f'/claims/{self.claim.id}/billing/item/add/',
            data=json.dumps({
                'description': 'Travel fee',
                'quantity': '1.00',
                'rate': '2000.00'
            }),
            content_type='application/json',
            HTTP_ACCEPT='application/json'
        )
        self.assertEqual(resp_add_locked.status_code, 400)
        self.assertEqual(resp_add_locked.json().get('code'), 'locked')

        # Edit locked
        resp_edit_locked = self.client.post(
            f'/claims/{self.claim.id}/billing/item/{item.id}/edit/',
            data=json.dumps({
                'description': 'Survey fee locked attempt',
                'quantity': '1.00',
                'rate': '18000.00'
            }),
            content_type='application/json',
            HTTP_ACCEPT='application/json'
        )
        self.assertEqual(resp_edit_locked.status_code, 400)
        self.assertEqual(resp_edit_locked.json().get('code'), 'locked')

    def test_claim_billing_mark_sent_payment_and_cancel(self):
        """claim_billing_mark_sent, claim_billing_record_payment, claim_billing_cancel."""
        self.client.force_login(self.admin_user)
        inv = ServiceInvoice.objects.create(
            claim=self.claim,
            due_date=date(2026, 9, 30),
            created_by=self.admin_user
        )

        # 1. Mark Sent via JSON
        resp_sent = self.client.post(
            f'/claims/{self.claim.id}/billing/mark-sent/',
            data=json.dumps({'base_updated_at': inv.updated_at.isoformat()}),
            content_type='application/json',
            HTTP_ACCEPT='application/json'
        )
        self.assertEqual(resp_sent.status_code, 200)
        inv.refresh_from_db()
        self.assertEqual(inv.status, ServiceInvoice.Status.SENT)

        # 2. Record payment via JSON
        resp_pay = self.client.post(
            f'/claims/{self.claim.id}/billing/record-payment/',
            data=json.dumps({
                'payment_reference': 'NEFT-12345678',
                'paid_date': '2026-09-20',
                'base_updated_at': inv.updated_at.isoformat()
            }),
            content_type='application/json',
            HTTP_ACCEPT='application/json'
        )
        self.assertEqual(resp_pay.status_code, 200)
        inv.refresh_from_db()
        self.assertEqual(inv.status, ServiceInvoice.Status.PAID)

        # 3. Create another invoice to test cancel
        claim2 = Claim.objects.create(
            survey_type=self.survey_type,
            insurer=self.insurer,
            insured=self.insured,
            policy=self.policy,
            instruction_date=date(2026, 9, 1),
            instruction_source='Email',
            date_of_loss=date(2026, 8, 30),
            nature_of_loss='Water damage',
            loss_location='Unit 2 Factory',
            claimed_amount=Decimal('20000.00'),
            created_by=self.admin_user
        )
        inv2 = ServiceInvoice.objects.create(
            claim=claim2,
            due_date=date(2026, 9, 30),
            created_by=self.admin_user
        )
        resp_cancel = self.client.post(
            f'/claims/{claim2.id}/billing/cancel/',
            data=json.dumps({'reason': 'Cancelled due to renegotiation'}),
            content_type='application/json',
            HTTP_ACCEPT='application/json'
        )
        self.assertEqual(resp_cancel.status_code, 200)
        inv2.refresh_from_db()
        self.assertEqual(inv2.status, ServiceInvoice.Status.CANCELLED)

    def test_claim_billing_item_delete_no_json_path(self):
        """Rule 3: claim_billing_item_delete has NO JSON path."""
        self.client.force_login(self.admin_user)
        inv = ServiceInvoice.objects.create(
            claim=self.claim,
            due_date=date(2026, 9, 30),
            created_by=self.admin_user
        )
        item = ServiceInvoiceItem.objects.create(
            invoice=inv,
            description='To Delete',
            quantity=Decimal('1.00'),
            rate=Decimal('500.00')
        )
        resp = self.client.post(
            f'/claims/{self.claim.id}/billing/item/{item.id}/delete/',
            data=json.dumps({}),
            content_type='application/json',
            HTTP_ACCEPT='application/json'
        )
        self.assertEqual(resp.status_code, 302)
