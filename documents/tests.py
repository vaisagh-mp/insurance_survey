from datetime import date
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from surveys.models import SurveyType
from claims.models import Insurer, Insured, Policy, Claim, Priority, ClaimStatus
from documents.models import DocumentType, ClaimDocument, Requirement
from documents.validators import (
    validate_document_extension,
    validate_file_size,
    validate_image_extension,
)

User = get_user_model()


class DocumentTypeSeededTests(TestCase):
    def test_seeded_document_types(self):
        expected_codes = [
            'POLICY', 'CLAIM_FORM', 'POLICE_REPORT', 'FIRE_BRIGADE_REPORT',
            'INVOICE', 'ESTIMATE', 'PURCHASE_INVOICE', 'SALES_INVOICE',
            'STOCK_REGISTER', 'VALUATION_CERTIFICATE', 'CA_CERTIFICATE',
            'WORK_ORDER', 'BILL_OF_ENTRY', 'FAR', 'PHOTOGRAPH',
            'ILA', 'ISR', 'FSR', 'OTHER'
        ]
        self.assertEqual(DocumentType.objects.count(), 19)
        actual_codes = list(DocumentType.objects.values_list('code', flat=True))
        for code in expected_codes:
            self.assertIn(code, actual_codes)


class DocumentModelTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_user(
            username='doc_admin',
            email='admin@doc.test',
            password='password123',
            role=User.Role.ADMIN
        )
        self.surveyor = User.objects.create_user(
            username='doc_surveyor',
            email='surveyor@doc.test',
            password='password123',
            role=User.Role.SURVEYOR
        )
        self.survey_type = SurveyType.objects.get(code='PROPERTY')

        self.insurer = Insurer.objects.create(
            company_name='Global Mutual Insurance',
            branch_name='Commercial Hub',
            address='50 Tower Way',
            city='Capital',
            state='State',
            pincode='500001',
            contact_person='Robert Vance',
            phone='+1-555-0300',
            email='claims@globalmutual.test'
        )
        self.insured = Insured.objects.create(
            name='Apex Retailers Pvt Ltd',
            company_name='Apex Group',
            address='12 Market Street',
            city='Capital',
            state='State',
            pincode='500002',
            phone='+1-555-0301',
            email='accounts@apexretail.test',
            contact_person='Sunil Patel'
        )
        now = timezone.now()
        self.policy = Policy.objects.create(
            insurer=self.insurer,
            policy_number='POL-PROP-2026-4411',
            policy_type='Commercial Property Comprehensive',
            start_datetime=now,
            end_datetime=now + timezone.timedelta(days=365),
            sum_insured=Decimal('15000000.00'),
            excess=Decimal('50000.00'),
            commodity='Retail Store Fixtures & Goods',
            subject_matter='Store Premise #4'
        )
        self.claim = Claim.objects.create(
            survey_type=self.survey_type,
            insurer=self.insurer,
            insured=self.insured,
            policy=self.policy,
            instruction_date=date(2026, 9, 14),
            instruction_source='Official claim intimation letter',
            date_of_loss=date(2026, 9, 13),
            nature_of_loss='Roof leakage collapse',
            loss_location='Retail Store #4, Ground Floor',
            claimed_amount=Decimal('850000.00'),
            priority=Priority.MEDIUM,
            status=ClaimStatus.NEW,
            created_by=self.admin_user
        )
        self.policy_doc_type = DocumentType.objects.get(code='POLICY')
        self.estimate_doc_type = DocumentType.objects.get(code='ESTIMATE')

    def test_claim_document_creation_and_validation(self):
        pdf_file = SimpleUploadedFile("policy_schedule.pdf", b"%PDF-1.4 mock content", content_type="application/pdf")
        doc = ClaimDocument.objects.create(
            claim=self.claim,
            document_type=self.policy_doc_type,
            file=pdf_file,
            document_number='POL-SCHED-01',
            document_date=date(2026, 1, 1),
            description='Signed original policy schedule document',
            uploaded_by=self.surveyor
        )

        self.assertEqual(doc.claim, self.claim)
        self.assertEqual(doc.document_type.code, 'POLICY')
        self.assertFalse(doc.verified)

        # Verification workflow
        doc.verified = True
        doc.verified_by = self.admin_user
        doc.verified_at = timezone.now()
        doc.remarks = 'Verified against underwriter master database'
        doc.save()

        self.assertTrue(doc.verified)
        self.assertEqual(doc.verified_by, self.admin_user)

    def test_document_validators(self):
        # Disallowed extension
        invalid_txt = SimpleUploadedFile("notes.txt", b"plain text", content_type="text/plain")
        with self.assertRaises(ValidationError):
            validate_document_extension(invalid_txt)

        # Allowed extensions
        for ext in ['pdf', 'jpg', 'jpeg', 'png']:
            valid_file = SimpleUploadedFile(f"file.{ext}", b"content", content_type="application/octet-stream")
            validate_document_extension(valid_file)

        # Disallowed size (>10MB)
        class MockOversized:
            size = 11 * 1024 * 1024

        with self.assertRaises(ValidationError) as ctx:
            validate_file_size(MockOversized())
        self.assertIn("cannot exceed 10MB", str(ctx.exception))

    def test_requirement_lor_item_workflow(self):
        req = Requirement.objects.create(
            claim=self.claim,
            description='Original repair estimate from authorized civil contractor',
            requested_from=Requirement.RequestedFrom.INSURED,
            requested_date=date(2026, 9, 15),
            due_date=date(2026, 9, 25),
            status=Requirement.Status.PENDING,
            created_by=self.surveyor
        )

        self.assertEqual(req.status, Requirement.Status.PENDING)
        self.assertIsNone(req.related_document)

        # When document is uploaded and linked
        estimate_file = SimpleUploadedFile("estimate.pdf", b"%PDF-1.4 estimate content", content_type="application/pdf")
        doc = ClaimDocument.objects.create(
            claim=self.claim,
            document_type=self.estimate_doc_type,
            file=estimate_file,
            document_number='EST-2026-99',
            uploaded_by=self.surveyor
        )

        req.related_document = doc
        req.status = Requirement.Status.RECEIVED
        req.received_date = date(2026, 9, 18)
        req.save()

        req.refresh_from_db()
        self.assertEqual(req.status, Requirement.Status.RECEIVED)
        self.assertEqual(req.related_document, doc)
        self.assertIn(req, self.claim.requirements.all())


class VerificationPermissionTests(DocumentModelTests):
    def setUp(self):
        super().setUp()
        from claims.models import SurveyAssignment
        SurveyAssignment.objects.create(
            claim=self.claim, surveyor=self.surveyor, assigned_by=self.admin_user,
            status=SurveyAssignment.Status.ASSIGNED, due_date=date(2026, 9, 30)
        )
        self.doc = ClaimDocument.objects.create(
            claim=self.claim, document_type=self.policy_doc_type,
            file=SimpleUploadedFile("doc.pdf", b"%PDF content", content_type="application/pdf"),
            uploaded_by=self.surveyor
        )
        self.req = Requirement.objects.create(
            claim=self.claim, description='Proof of loss',
            requested_from=Requirement.RequestedFrom.INSURED,
            requested_date=date(2026, 9, 1), status=Requirement.Status.PENDING,
            created_by=self.surveyor
        )

    def test_surveyor_cannot_verify_claim_document_via_web(self):
        self.client.force_login(self.surveyor)
        response = self.client.post(f'/claims/{self.claim.pk}/documents/{self.doc.pk}/verify/')
        self.assertEqual(response.status_code, 403)
        self.doc.refresh_from_db()
        self.assertFalse(self.doc.verified)

    def test_admin_can_verify_claim_document_via_web(self):
        self.client.force_login(self.admin_user)
        response = self.client.post(f'/claims/{self.claim.pk}/documents/{self.doc.pk}/verify/')
        self.assertEqual(response.status_code, 302)
        self.doc.refresh_from_db()
        self.assertTrue(self.doc.verified)
        self.assertEqual(self.doc.verified_by, self.admin_user)

    def test_surveyor_cannot_set_requirement_to_verified_via_web(self):
        self.client.force_login(self.surveyor)
        response = self.client.post(f'/claims/{self.claim.pk}/lor/{self.req.pk}/update-status/', {'status': 'VERIFIED'})
        self.assertEqual(response.status_code, 302)
        self.req.refresh_from_db()
        self.assertEqual(self.req.status, Requirement.Status.PENDING)

    def test_admin_can_set_requirement_to_verified_via_web(self):
        self.client.force_login(self.admin_user)
        response = self.client.post(f'/claims/{self.claim.pk}/lor/{self.req.pk}/update-status/', {'status': 'VERIFIED'})
        self.assertEqual(response.status_code, 302)
        self.req.refresh_from_db()
        self.assertEqual(self.req.status, Requirement.Status.VERIFIED)

    def test_surveyor_can_update_requirement_to_received(self):
        self.client.force_login(self.surveyor)
        response = self.client.post(f'/claims/{self.claim.pk}/lor/{self.req.pk}/update-status/', {'status': 'RECEIVED'})
        self.assertEqual(response.status_code, 302)
        self.req.refresh_from_db()
        self.assertEqual(self.req.status, Requirement.Status.RECEIVED)
