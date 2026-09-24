from datetime import date
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.utils import timezone
from surveys.models import SurveyType
from claims.models import Insurer, Insured, Policy, Claim, Priority, ClaimStatus, SurveyAssignment
from assessments.models import Invoice, Assessment, AssessmentItem
from assessments.services import recalculate_assessment

User = get_user_model()


class AssessmentTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_user(
            username='assess_admin',
            email='admin@assess.test',
            password='password123',
            role=User.Role.ADMIN
        )
        self.surveyor = User.objects.create_user(
            username='assess_surveyor',
            email='surveyor@assess.test',
            password='password123',
            role=User.Role.SURVEYOR
        )
        self.survey_type = SurveyType.objects.get(code='ENG')

        self.insurer = Insurer.objects.create(
            company_name='Industrial Mutual Insurance',
            branch_name='Engineering Hub',
            address='1 Industrial Way',
            city='Metro City',
            state='State',
            pincode='700001',
            contact_person='Kevin Scott',
            phone='+1-555-0500',
            email='claims@industrialmutual.test'
        )
        self.insured = Insured.objects.create(
            name='Precision Tech Ltd',
            company_name='Precision Group',
            address='Plot 5 Tech Zone',
            city='Metro City',
            state='State',
            pincode='700002',
            phone='+1-555-0501',
            email='accounts@precisiontech.test',
            contact_person='Deepak Roy'
        )
        now = timezone.now()
        self.policy = Policy.objects.create(
            insurer=self.insurer,
            policy_number='POL-ENG-2026-8801',
            policy_type='Machinery Breakdown Policy',
            start_datetime=now,
            end_datetime=now + timezone.timedelta(days=365),
            sum_insured=Decimal('10000000.00'),
            excess=Decimal('5000.00'),
            commodity='CNC Milling Center & Spindle Assembly',
            subject_matter='Machine Shop #1'
        )
        self.claim = Claim.objects.create(
            survey_type=self.survey_type,
            insurer=self.insurer,
            insured=self.insured,
            policy=self.policy,
            instruction_date=date(2026, 9, 15),
            instruction_source='Intimation portal',
            date_of_loss=date(2026, 9, 14),
            nature_of_loss='Spindle bearing seizure and drive motor burnout',
            loss_location='Machine Shop #1, Bay 3',
            claimed_amount=Decimal('600000.00'),
            priority=Priority.HIGH,
            status=ClaimStatus.ASSESSMENT_IN_PROGRESS,
            created_by=self.admin_user
        )
        self.assignment = SurveyAssignment.objects.create(
            claim=self.claim,
            surveyor=self.surveyor,
            assigned_by=self.admin_user,
            due_date=date(2026, 9, 30),
            status=SurveyAssignment.Status.ASSIGNED
        )

    def test_invoice_creation_and_validation(self):
        pdf_invoice = SimpleUploadedFile("vendor_inv_01.pdf", b"%PDF-1.4 sample invoice", content_type="application/pdf")
        inv = Invoice.objects.create(
            claim=self.claim,
            invoice_number='INV-2026-9001',
            invoice_date=date(2026, 9, 16),
            vendor_name='Apex Engineering Spares',
            description='Replacement ceramic spindle bearings and drive belts',
            amount=Decimal('150000.00'),
            tax_amount=Decimal('27000.00'),
            total_amount=Decimal('177000.00'),
            document=pdf_invoice
        )

        self.assertEqual(inv.total_amount, Decimal('177000.00'))
        self.assertFalse(inv.verified)

        # Verification
        inv.verified = True
        inv.verified_by = self.admin_user
        inv.remarks = 'Cross-checked with GST portal tax invoice'
        inv.save()

        self.assertTrue(inv.verified)
        self.assertEqual(inv.verified_by, self.admin_user)

    def test_recalculate_assessment_worked_example(self):
        """
        Reproduce the spec's worked example:
        Gross: 550,000
        Underinsurance: 201,300 (via 36.6% underinsurance percentage on 550,000)
        Adjusted: 348,700
        Excess: 5,000
        Net: 343,700
        """
        assessment = Assessment.objects.create(
            claim=self.claim,
            underinsurance_percentage=Decimal('36.60'),
            policy_excess=Decimal('5000.00'),
            salvage_amount=Decimal('0.00'),
            depreciation_amount=Decimal('0.00'),
            other_deductions=Decimal('0.00'),
            created_by=self.admin_user
        )

        # Add items totaling 550,000
        # Item 1: 2 units @ 150,000 = 300,000
        AssessmentItem.objects.create(
            assessment=assessment,
            item_code='SP-01',
            description='Spindle ceramic bearing set',
            quantity=Decimal('2.00'),
            rate=Decimal('150000.00'),
            claimed_amount=Decimal('320000.00')
        )

        # Item 2: 1 unit @ 250,000 = 250,000
        AssessmentItem.objects.create(
            assessment=assessment,
            item_code='MO-02',
            description='AC servo spindle motor replacement',
            quantity=Decimal('1.00'),
            rate=Decimal('250000.00'),
            claimed_amount=Decimal('280000.00')
        )

        # Trigger service recalculation
        recalculate_assessment(assessment)
        assessment.refresh_from_db()

        self.assertEqual(assessment.gross_assessed_loss, Decimal('550000.00'))
        self.assertEqual(assessment.underinsurance_amount, Decimal('201300.00'))
        self.assertEqual(assessment.adjusted_loss, Decimal('348700.00'))
        self.assertEqual(assessment.policy_excess, Decimal('5000.00'))
        self.assertEqual(assessment.net_assessed_loss, Decimal('343700.00'))

    def test_recalculate_assessment_with_salvage_and_depreciation(self):
        assessment = Assessment.objects.create(
            claim=self.claim,
            salvage_amount=Decimal('20000.00'),
            depreciation_amount=Decimal('30000.00'),
            underinsurance_percentage=Decimal('10.00'),
            policy_excess=Decimal('10000.00'),
            other_deductions=Decimal('5000.00'),
            created_by=self.admin_user
        )

        # 1 item @ 200,000
        AssessmentItem.objects.create(
            assessment=assessment,
            description='Replacement assembly',
            quantity=Decimal('1.00'),
            rate=Decimal('200000.00'),
            claimed_amount=Decimal('220000.00')
        )

        recalculate_assessment(assessment)
        assessment.refresh_from_db()

        # Gross: 200,000
        # Underinsurance: 10% of 200,000 = 20,000
        # Adjusted: 200,000 - 20,000 (salvage) - 20,000 (underinsurance) - 30,000 (depreciation) = 130,000
        # Net: 130,000 - 10,000 (excess) - 5,000 (other) = 115,000
        self.assertEqual(assessment.gross_assessed_loss, Decimal('200000.00'))
        self.assertEqual(assessment.underinsurance_amount, Decimal('20000.00'))
        self.assertEqual(assessment.adjusted_loss, Decimal('130000.00'))
        self.assertEqual(assessment.net_assessed_loss, Decimal('115000.00'))

    def test_net_loss_floor_at_zero(self):
        assessment = Assessment.objects.create(
            claim=self.claim,
            policy_excess=Decimal('50000.00'),
            salvage_amount=Decimal('10000.00'),
            created_by=self.admin_user
        )
        AssessmentItem.objects.create(
            assessment=assessment,
            description='Minor part',
            quantity=Decimal('1.00'),
            rate=Decimal('10000.00'),
            claimed_amount=Decimal('15000.00')
        )

        recalculate_assessment(assessment)
        assessment.refresh_from_db()

        # Gross: 10,000, Salvage: 10,000 -> Adjusted: 0, Excess: 50,000 -> Net cannot be negative
        self.assertEqual(assessment.net_assessed_loss, Decimal('0.00'))

    def test_surveyor_can_add_repair_invoice_via_web(self):
        client = Client()
        client.force_login(self.surveyor)

        pdf_doc = SimpleUploadedFile("workshop_bill.pdf", b"%PDF-1.4 sample bill", content_type="application/pdf")
        url = f"/claims/{self.claim.id}/invoices/add/"
        response = client.post(url, {
            'invoice_number': 'BILL-2026-0044',
            'invoice_date': '2026-09-18',
            'vendor_name': 'Precision Motors Workshop',
            'amount': '45000.00',
            'tax_amount': '8100.00',
            'description': 'Machinery shaft realignment and replacement seal kit',
            'remarks': 'Inspected during site visit #2',
            'document': pdf_doc
        }, follow=True)

        self.assertEqual(response.status_code, 200)
        inv = Invoice.objects.filter(claim=self.claim, invoice_number='BILL-2026-0044').first()
        self.assertIsNotNone(inv)
        self.assertEqual(inv.vendor_name, 'Precision Motors Workshop')
        self.assertEqual(inv.amount, Decimal('45000.00'))
        self.assertEqual(inv.tax_amount, Decimal('8100.00'))
        self.assertEqual(inv.total_amount, Decimal('53100.00'))
        self.assertFalse(inv.verified)
        self.assertTrue(bool(inv.document))

    def test_surveyor_can_delete_repair_invoice_via_web(self):
        client = Client()
        client.force_login(self.surveyor)

        inv = Invoice.objects.create(
            claim=self.claim,
            invoice_number='TEMP-DELETE-01',
            invoice_date=date(2026, 9, 18),
            vendor_name='Temp Vendor',
            amount=Decimal('5000.00'),
            tax_amount=Decimal('0.00'),
            total_amount=Decimal('5000.00')
        )

        url = f"/claims/{self.claim.id}/invoices/{inv.id}/delete/"
        response = client.post(url, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Invoice.objects.filter(id=inv.id).exists())

    def test_admin_can_toggle_invoice_verification_via_web(self):
        client = Client()
        client.force_login(self.admin_user)

        inv = Invoice.objects.create(
            claim=self.claim,
            invoice_number='INV-TO-VERIFY-01',
            invoice_date=date(2026, 9, 18),
            vendor_name='Certified Spares Co',
            amount=Decimal('12000.00'),
            tax_amount=Decimal('2160.00'),
            total_amount=Decimal('14160.00'),
            verified=False
        )

        url = f"/claims/{self.claim.id}/invoices/{inv.id}/verify/"
        response = client.post(url, follow=True)
        self.assertEqual(response.status_code, 200)
        inv.refresh_from_db()
        self.assertTrue(inv.verified)
        self.assertEqual(inv.verified_by, self.admin_user)

    def test_unassigned_surveyor_forbidden_from_adding_invoice(self):
        unassigned_surveyor = User.objects.create_user(
            username='other_surveyor',
            email='other@assess.test',
            password='password123',
            role=User.Role.SURVEYOR
        )
        client = Client()
        client.force_login(unassigned_surveyor)

        url = f"/claims/{self.claim.id}/invoices/add/"
        response = client.post(url, {
            'invoice_number': 'FORBIDDEN-01',
            'invoice_date': '2026-09-18',
            'vendor_name': 'Unauthorized',
            'amount': '1000.00',
        })
        self.assertEqual(response.status_code, 403)

