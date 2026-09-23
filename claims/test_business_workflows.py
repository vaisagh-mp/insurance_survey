from datetime import date, time
from decimal import Decimal
from io import BytesIO
from PIL import Image

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError, PermissionDenied
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken

from surveys.models import SurveyType, Inspection, InspectionPhoto
from claims.models import (
    Insurer,
    Insured,
    Policy,
    Claim,
    ClaimStatus,
    ClaimStatusHistory,
    SurveyAssignment,
    Priority,
)
from claims.services import (
    ALLOWED_TRANSITIONS,
    transition_claim_status,
    assign_surveyor,
    close_claim,
)
from documents.models import DocumentType, ClaimDocument
from documents.validators import (
    validate_document_file,
    validate_image_file,
    validate_file_size,
)
from assessments.models import Assessment, AssessmentItem, Invoice
from assessments.services import recalculate_assessment, round_curr
from assessments.forms import AssessmentItemForm
from assessments.serializers import AssessmentItemSerializer
from reports.models import AuditLog, ILA, ISR, FSR, ReportStatus

User = get_user_model()


def make_test_image(filename="test.jpg"):
    stream = BytesIO()
    img = Image.new("RGB", (40, 40), color=(120, 20, 30))
    img.save(stream, format="JPEG")
    stream.seek(0)
    return SimpleUploadedFile(filename, stream.read(), content_type="image/jpeg")


def make_test_pdf(filename="test.pdf"):
    return SimpleUploadedFile(
        filename,
        b"%PDF-1.4 test business document content %%EOF",
        content_type="application/pdf"
    )


class BaseWorkflowTestCase(TestCase):
    """Common setup for claims business testing."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username='wf_admin',
            email='admin@workflow.test',
            password='Password123!',
            role=User.Role.ADMIN
        )
        self.surveyor_a = User.objects.create_user(
            username='wf_surveyor_a',
            email='surv_a@workflow.test',
            password='Password123!',
            role=User.Role.SURVEYOR
        )
        self.surveyor_b = User.objects.create_user(
            username='wf_surveyor_b',
            email='surv_b@workflow.test',
            password='Password123!',
            role=User.Role.SURVEYOR
        )

        self.survey_type = SurveyType.objects.get(code='FIRE')

        self.insurer = Insurer.objects.create(
            company_name='Reliable Insurance Co',
            branch_name='North Zone HQ',
            address='100 Finance St',
            city='Capital City',
            state='State',
            pincode='110001',
            contact_person='Frank Manager',
            phone='+1-555-4001',
            email='claims@reliable.test'
        )

        self.insured = Insured.objects.create(
            name='Vertex Industrial Hub Ltd',
            company_name='Vertex Group',
            address='Sector 4 Industrial Area',
            city='Capital City',
            state='State',
            pincode='110002',
            phone='+1-555-4002',
            email='info@vertex.test',
            contact_person='Sarah Connor'
        )

        now = timezone.now()
        self.policy = Policy.objects.create(
            insurer=self.insurer,
            policy_number='POL-WF-2026-001',
            policy_type='Standard Fire & Special Perils',
            start_datetime=now - timezone.timedelta(days=30),
            end_datetime=now + timezone.timedelta(days=335),
            sum_insured=Decimal('5000000.00'),
            excess=Decimal('5000.00'),
            commodity='Industrial Machinery & Stocks',
            subject_matter='Factory Plant unit 1'
        )

        self.claim = Claim.objects.create(
            claim_number='CLM-WF-001',
            survey_type=self.survey_type,
            insurer=self.insurer,
            insured=self.insured,
            policy=self.policy,
            instruction_date=date(2026, 9, 1),
            instruction_source='Regional Underwriter',
            date_of_loss=date(2026, 8, 28),
            nature_of_loss='Fire outbreak in main electrical panel',
            loss_location='Sector 4 Industrial Area',
            claimed_amount=Decimal('550000.00'),
            priority=Priority.HIGH,
            status=ClaimStatus.NEW,
            created_by=self.admin
        )


class ClaimWorkflowTransitionTests(BaseWorkflowTestCase):
    """
    Tests for status transitions across the FULL 17-status lifecycle:
    - Every valid transition in ALLOWED_TRANSITIONS succeeds and writes 1 ClaimStatusHistory row.
    - Representative invalid transitions are rejected and write 0 ClaimStatusHistory rows.
    """

    def test_full_17_statuses_defined_in_allowed_transitions(self):
        """Verify that all 17 ClaimStatus choices are represented in ALLOWED_TRANSITIONS."""
        all_choices = set(ClaimStatus.values)
        self.assertEqual(len(all_choices), 17)
        self.assertEqual(set(ALLOWED_TRANSITIONS.keys()), all_choices)

    def test_every_valid_transition_across_full_17_statuses(self):
        """
        Exercise every single valid transition defined in ALLOWED_TRANSITIONS.
        Assert that each:
        1. Updates claim.status to target status.
        2. Inserts exactly one ClaimStatusHistory record with correct old/new status and changed_by.
        3. Creates an AuditLog entry.
        """
        for from_status, target_statuses in ALLOWED_TRANSITIONS.items():
            for to_status in target_statuses:
                # Reset claim to the origin status
                Claim.objects.filter(id=self.claim.id).update(status=from_status)
                self.claim.refresh_from_db()
                self.assertEqual(self.claim.status, from_status)

                initial_history_count = ClaimStatusHistory.objects.filter(claim=self.claim).count()
                initial_audit_count = AuditLog.objects.filter(claim=self.claim).count()

                # Perform the transition
                transition_claim_status(
                    claim=self.claim,
                    new_status=to_status,
                    user=self.admin,
                    remarks=f"Testing transition from {from_status} to {to_status}"
                )

                self.claim.refresh_from_db()
                self.assertEqual(
                    self.claim.status,
                    to_status,
                    f"Failed to transition from {from_status} to {to_status}"
                )

                # Exactly 1 new history row created
                new_history_count = ClaimStatusHistory.objects.filter(claim=self.claim).count()
                self.assertEqual(
                    new_history_count,
                    initial_history_count + 1,
                    f"Expected 1 history row from {from_status} -> {to_status}"
                )
                latest_history = ClaimStatusHistory.objects.filter(claim=self.claim).latest('changed_at')
                self.assertEqual(latest_history.old_status, from_status)
                self.assertEqual(latest_history.new_status, to_status)
                self.assertEqual(latest_history.changed_by, self.admin)

                # Exactly 1 new audit log entry
                new_audit_count = AuditLog.objects.filter(claim=self.claim).count()
                self.assertEqual(
                    new_audit_count,
                    initial_audit_count + 1,
                    f"Expected 1 audit log row from {from_status} -> {to_status}"
                )

    def test_representative_invalid_transitions_rejected(self):
        """
        Verify that nonsensical or prohibited transitions are rejected with ValidationError,
        status remains unchanged, and zero ClaimStatusHistory rows are written.
        """
        invalid_pairs = [
            (ClaimStatus.NEW, ClaimStatus.CLOSED),
            (ClaimStatus.NEW, ClaimStatus.FSR_PREPARED),
            (ClaimStatus.NEW, ClaimStatus.REPORT_SUBMITTED),
            (ClaimStatus.ASSIGNED, ClaimStatus.CLOSED),
            (ClaimStatus.INSPECTION_PENDING, ClaimStatus.CLOSED),
            (ClaimStatus.DOCUMENT_COLLECTION, ClaimStatus.NEW),
            (ClaimStatus.DOCUMENT_COLLECTION, ClaimStatus.CLOSED),
            (ClaimStatus.CLOSED, ClaimStatus.NEW),
            (ClaimStatus.CLOSED, ClaimStatus.ASSIGNED),
            (ClaimStatus.CLOSED, ClaimStatus.FSR_PREPARED),
            (ClaimStatus.CANCELLED, ClaimStatus.CLOSED),
            (ClaimStatus.CANCELLED, ClaimStatus.FSR_PREPARED),
            (ClaimStatus.REPORT_SUBMITTED, ClaimStatus.NEW),
            (ClaimStatus.REPORT_SUBMITTED, ClaimStatus.INSPECTION_PENDING),
            (ClaimStatus.QUERY_RAISED, ClaimStatus.NEW),
            (ClaimStatus.QUERY_RAISED, ClaimStatus.CLOSED),
        ]

        for from_status, invalid_to in invalid_pairs:
            Claim.objects.filter(id=self.claim.id).update(status=from_status)
            self.claim.refresh_from_db()

            initial_history_count = ClaimStatusHistory.objects.filter(claim=self.claim).count()
            initial_audit_count = AuditLog.objects.filter(claim=self.claim).count()

            with self.assertRaises(ValidationError, msg=f"Should reject {from_status} -> {invalid_to}"):
                transition_claim_status(
                    claim=self.claim,
                    new_status=invalid_to,
                    user=self.admin
                )

            self.claim.refresh_from_db()
            self.assertEqual(self.claim.status, from_status)

            # Zero rows written
            self.assertEqual(
                ClaimStatusHistory.objects.filter(claim=self.claim).count(),
                initial_history_count,
                f"History must not be written on rejected transition {from_status} -> {invalid_to}"
            )
            self.assertEqual(
                AuditLog.objects.filter(claim=self.claim).count(),
                initial_audit_count,
                f"AuditLog must not be written on rejected transition {from_status} -> {invalid_to}"
            )


class CloseClaimGuardTests(BaseWorkflowTestCase):
    """
    Dedicated test suite for close_claim service guard:
    - Rejects closing when no report is FINAL (with 0 history rows and unchanged status).
    - Succeeds when at least one report is marked FINAL (transitions to CLOSED, writes 1 history row).
    """

    def setUp(self):
        super().setUp()
        Claim.objects.filter(id=self.claim.id).update(status=ClaimStatus.FSR_PREPARED)
        self.claim.refresh_from_db()

    def test_close_claim_rejected_when_no_reports_exist(self):
        """close_claim must raise ValidationError if claim has zero reports."""
        initial_history_count = ClaimStatusHistory.objects.filter(claim=self.claim).count()

        with self.assertRaises(ValidationError) as ctx:
            close_claim(self.claim, self.admin)

        self.assertIn("FINAL", str(ctx.exception))
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, ClaimStatus.FSR_PREPARED)
        self.assertEqual(
            ClaimStatusHistory.objects.filter(claim=self.claim).count(),
            initial_history_count
        )

    def test_close_claim_rejected_when_reports_are_draft_submitted_or_query(self):
        """close_claim must raise ValidationError if existing reports are not FINAL."""
        fsr = FSR.objects.create(
            claim=self.claim,
            report_number='FSR-GUARD-01',
            report_date=date(2026, 9, 20),
            status=ReportStatus.DRAFT,
            prepared_by=self.surveyor_a,
            value_at_risk=Decimal('500000.00'),
            sum_insured=Decimal('500000.00'),
            admissibility='Admissible',
            policy_coverage='Standard',
            final_opinion='Pending finalize'
        )

        with self.assertRaises(ValidationError) as ctx:
            close_claim(self.claim, self.admin)
        self.assertIn("FINAL", str(ctx.exception))

        # Try with SUBMITTED status
        fsr.status = ReportStatus.SUBMITTED
        fsr.save()
        with self.assertRaises(ValidationError) as ctx:
            close_claim(self.claim, self.admin)
        self.assertIn("FINAL", str(ctx.exception))

        # Try with QUERY status
        fsr.status = ReportStatus.QUERY
        fsr.save()
        with self.assertRaises(ValidationError) as ctx:
            close_claim(self.claim, self.admin)
        self.assertIn("FINAL", str(ctx.exception))

        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, ClaimStatus.FSR_PREPARED)

    def test_close_claim_succeeds_when_at_least_one_report_is_final(self):
        """close_claim succeeds and transitions claim to CLOSED once an FSR/ISR/ILA is marked FINAL."""
        fsr = FSR.objects.create(
            claim=self.claim,
            report_number='FSR-GUARD-02',
            report_date=date(2026, 9, 20),
            status=ReportStatus.FINAL,
            prepared_by=self.surveyor_a,
            value_at_risk=Decimal('500000.00'),
            sum_insured=Decimal('500000.00'),
            admissibility='Admissible',
            policy_coverage='Standard',
            final_opinion='Claim assessment complete and accepted.'
        )

        initial_history_count = ClaimStatusHistory.objects.filter(claim=self.claim).count()
        close_claim(self.claim, self.admin, remarks="All inspections and final report accepted.")

        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, ClaimStatus.CLOSED)

        # 1 history row written
        new_history_count = ClaimStatusHistory.objects.filter(claim=self.claim).count()
        self.assertEqual(new_history_count, initial_history_count + 1)
        history = ClaimStatusHistory.objects.filter(claim=self.claim).latest('changed_at')
        self.assertEqual(history.old_status, ClaimStatus.FSR_PREPARED)
        self.assertEqual(history.new_status, ClaimStatus.CLOSED)
        self.assertEqual(history.changed_by, self.admin)


class AssessmentCalculationAndValidationTests(BaseWorkflowTestCase):
    """
    Dedicated tests for assessment financial calculations:
    - Item quantity × rate calculation.
    - Spec's worked example: Gross 550,000 → Net 343,700.
    - Negative quantity or rate rejected by validation.
    - Zero values and rounding behavior.
    """

    def setUp(self):
        super().setUp()
        self.assessment = Assessment.objects.create(
            claim=self.claim,
            underinsurance_percentage=Decimal('36.60'),
            policy_excess=Decimal('5000.00'),
            salvage_amount=Decimal('0.00'),
            depreciation_amount=Decimal('0.00'),
            other_deductions=Decimal('0.00'),
            created_by=self.admin
        )

    def test_assessment_worked_example_550k_to_343700(self):
        """
        Reproduce the spec's exact worked example:
        Gross: 550,000
        Underinsurance: 201,300 (36.60% of 550,000)
        Adjusted: 348,700
        Excess: 5,000
        Net: 343,700
        """
        # Item 1: 2 units @ 150,000 = 300,000
        item1 = AssessmentItem.objects.create(
            assessment=self.assessment,
            item_code='SP-01',
            description='Spindle ceramic bearing set',
            quantity=Decimal('2.00'),
            rate=Decimal('150000.00'),
            claimed_amount=Decimal('320000.00')
        )
        self.assertEqual(item1.assessed_amount, Decimal('300000.00'))

        # Item 2: 1 unit @ 250,000 = 250,000
        item2 = AssessmentItem.objects.create(
            assessment=self.assessment,
            item_code='MO-02',
            description='AC servo spindle motor replacement',
            quantity=Decimal('1.00'),
            rate=Decimal('250000.00'),
            claimed_amount=Decimal('280000.00')
        )
        self.assertEqual(item2.assessed_amount, Decimal('250000.00'))

        # Run recalculation service
        recalculate_assessment(self.assessment)
        self.assessment.refresh_from_db()

        self.assertEqual(self.assessment.gross_assessed_loss, Decimal('550000.00'))
        self.assertEqual(self.assessment.underinsurance_amount, Decimal('201300.00'))
        self.assertEqual(self.assessment.adjusted_loss, Decimal('348700.00'))
        self.assertEqual(self.assessment.policy_excess, Decimal('5000.00'))
        self.assertEqual(self.assessment.net_assessed_loss, Decimal('343700.00'))

    def test_negative_quantity_or_rate_rejected_by_model_validation(self):
        """AssessmentItem rejects negative quantity or rate at model full_clean()."""
        # Negative quantity
        item_neg_qty = AssessmentItem(
            assessment=self.assessment,
            description='Defective Motor',
            quantity=Decimal('-1.00'),
            rate=Decimal('1000.00'),
            claimed_amount=Decimal('1000.00')
        )
        with self.assertRaises(ValidationError) as ctx:
            item_neg_qty.full_clean()
        self.assertIn('quantity', ctx.exception.message_dict)

        # Negative rate
        item_neg_rate = AssessmentItem(
            assessment=self.assessment,
            description='Defective Motor',
            quantity=Decimal('2.00'),
            rate=Decimal('-500.00'),
            claimed_amount=Decimal('1000.00')
        )
        with self.assertRaises(ValidationError) as ctx:
            item_neg_rate.full_clean()
        self.assertIn('rate', ctx.exception.message_dict)

    def test_negative_quantity_or_rate_rejected_by_form_and_serializer(self):
        """AssessmentItemForm and AssessmentItemSerializer reject negative inputs."""
        # Form test
        form = AssessmentItemForm(data={
            'description': 'Spare Part',
            'quantity': '-2.00',
            'rate': '500.00',
            'claimed_amount': '1000.00'
        })
        self.assertFalse(form.is_valid())
        self.assertIn('quantity', form.errors)

        form_rate = AssessmentItemForm(data={
            'description': 'Spare Part',
            'quantity': '2.00',
            'rate': '-500.00',
            'claimed_amount': '1000.00'
        })
        self.assertFalse(form_rate.is_valid())
        self.assertIn('rate', form_rate.errors)

        # Serializer test
        serializer_qty = AssessmentItemSerializer(data={
            'description': 'Spare Part',
            'quantity': '-3.00',
            'rate': '100.00',
            'claimed_amount': '300.00'
        })
        self.assertFalse(serializer_qty.is_valid())
        self.assertIn('quantity', serializer_qty.errors)

        serializer_rate = AssessmentItemSerializer(data={
            'description': 'Spare Part',
            'quantity': '3.00',
            'rate': '-100.00',
            'claimed_amount': '300.00'
        })
        self.assertFalse(serializer_rate.is_valid())
        self.assertIn('rate', serializer_rate.errors)

    def test_zero_values_and_rounding_behavior(self):
        """Zero values are valid and rounding behaves deterministically."""
        # Zero quantity and zero rate are valid
        zero_item = AssessmentItem(
            assessment=self.assessment,
            description='Zero salvage spare',
            quantity=Decimal('0.00'),
            rate=Decimal('0.00'),
            claimed_amount=Decimal('0.00')
        )
        zero_item.full_clean()
        zero_item.save()
        self.assertEqual(zero_item.assessed_amount, Decimal('0.00'))

        # round_curr helper handles None safely
        self.assertEqual(round_curr(None), Decimal('0.00'))
        self.assertEqual(round_curr(Decimal('123.456')), Decimal('123.46'))

        # Net loss is clamped at zero if deductions exceed adjusted loss
        self.assessment.policy_excess = Decimal('1000000.00')
        recalculate_assessment(self.assessment)
        self.assessment.refresh_from_db()
        self.assertEqual(self.assessment.net_assessed_loss, Decimal('0.00'))


class CrossSurveyorIsolationAndPermissionTests(APITestCase):
    """
    Tests ensuring full isolation between surveyors:
    - Admin can view all claims.
    - Surveyor can view only their assigned claims.
    - Surveyor A cannot view Surveyor B's claim by API and by direct web URL.
    - Surveyor cannot access user management or master data mutation endpoints.
    """

    def setUp(self):
        self.admin = User.objects.create_user(
            username='perm_admin',
            email='admin@perm.test',
            password='Password123!',
            role=User.Role.ADMIN
        )
        self.surveyor_a = User.objects.create_user(
            username='perm_surveyor_a',
            email='surv_a@perm.test',
            password='Password123!',
            role=User.Role.SURVEYOR
        )
        self.surveyor_b = User.objects.create_user(
            username='perm_surveyor_b',
            email='surv_b@perm.test',
            password='Password123!',
            role=User.Role.SURVEYOR
        )

        self.survey_type = SurveyType.objects.get(code='FIRE')
        self.insurer = Insurer.objects.create(
            company_name='Perm Insurer',
            branch_name='HQ',
            address='Addr',
            city='City',
            state='State',
            pincode='123456',
            contact_person='Contact',
            phone='1234567890',
            email='ins@perm.test'
        )
        self.insured = Insured.objects.create(
            name='Perm Insured',
            company_name='Perm Corp',
            address='Addr',
            city='City',
            state='State',
            pincode='123456',
            phone='1234567890',
            email='insured@perm.test'
        )
        now = timezone.now()
        self.policy = Policy.objects.create(
            insurer=self.insurer,
            policy_number='POL-PERM-01',
            policy_type='Fire Policy',
            start_datetime=now,
            end_datetime=now + timezone.timedelta(days=365),
            sum_insured=Decimal('1000000.00'),
            excess=Decimal('5000.00'),
            commodity='Goods',
            subject_matter='Stock'
        )

        # Claim 1 -> assigned to Surveyor A
        self.claim_1 = Claim.objects.create(
            claim_number='CLM-PERM-001',
            survey_type=self.survey_type,
            insurer=self.insurer,
            insured=self.insured,
            policy=self.policy,
            instruction_date=date(2026, 9, 1),
            instruction_source='Email',
            date_of_loss=date(2026, 8, 30),
            nature_of_loss='Fire in Plant A',
            loss_location='Plant A',
            claimed_amount=Decimal('100000.00'),
            status=ClaimStatus.ASSIGNED,
            created_by=self.admin
        )
        SurveyAssignment.objects.create(
            claim=self.claim_1,
            surveyor=self.surveyor_a,
            assigned_by=self.admin,
            due_date=date(2026, 9, 25),
            status=SurveyAssignment.Status.ASSIGNED
        )

        # Claim 2 -> assigned to Surveyor B
        self.claim_2 = Claim.objects.create(
            claim_number='CLM-PERM-002',
            survey_type=self.survey_type,
            insurer=self.insurer,
            insured=self.insured,
            policy=self.policy,
            instruction_date=date(2026, 9, 2),
            instruction_source='Email',
            date_of_loss=date(2026, 8, 31),
            nature_of_loss='Fire in Plant B',
            loss_location='Plant B',
            claimed_amount=Decimal('200000.00'),
            status=ClaimStatus.ASSIGNED,
            created_by=self.admin
        )
        SurveyAssignment.objects.create(
            claim=self.claim_2,
            surveyor=self.surveyor_b,
            assigned_by=self.admin,
            due_date=date(2026, 9, 26),
            status=SurveyAssignment.Status.ASSIGNED
        )

    def test_admin_can_view_and_list_all_claims(self):
        """Admin can list all claims via API and view all claims via Web UI."""
        # 1. API check
        token = RefreshToken.for_user(self.admin).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        api_resp = self.client.get('/api/claims/')
        self.assertEqual(api_resp.status_code, status.HTTP_200_OK)
        results = api_resp.data.get('results', api_resp.data)
        ids = [item['id'] for item in results]
        self.assertIn(self.claim_1.id, ids)
        self.assertIn(self.claim_2.id, ids)

        # 2. Web check
        django_client = Client()
        django_client.force_login(self.admin)
        web_list = django_client.get('/claims/')
        self.assertEqual(web_list.status_code, 200)
        self.assertContains(web_list, self.claim_1.claim_number)
        self.assertContains(web_list, self.claim_2.claim_number)

        web_detail_1 = django_client.get(f'/claims/{self.claim_1.id}/')
        self.assertEqual(web_detail_1.status_code, 200)
        web_detail_2 = django_client.get(f'/claims/{self.claim_2.id}/')
        self.assertEqual(web_detail_2.status_code, 200)

    def test_surveyor_can_view_only_assigned_claims(self):
        """Surveyor list endpoint returns only claims assigned to that surveyor."""
        # Surveyor A API list
        token_a = RefreshToken.for_user(self.surveyor_a).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token_a}')
        resp_a = self.client.get('/api/claims/')
        self.assertEqual(resp_a.status_code, status.HTTP_200_OK)
        results_a = resp_a.data.get('results', resp_a.data)
        ids_a = [item['id'] for item in results_a]
        self.assertIn(self.claim_1.id, ids_a)
        self.assertNotIn(self.claim_2.id, ids_a)

        # Surveyor A Web list
        django_client = Client()
        django_client.force_login(self.surveyor_a)
        web_list_a = django_client.get('/claims/')
        self.assertEqual(web_list_a.status_code, 200)
        self.assertContains(web_list_a, self.claim_1.claim_number)
        self.assertNotContains(web_list_a, self.claim_2.claim_number)

    def test_surveyor_a_cannot_view_surveyor_b_claim_by_api_and_direct_url(self):
        """
        Cross-surveyor isolation:
        Surveyor A requesting Surveyor B's claim is blocked both via API (403/404)
        and via direct HTML workspace URL (403 Forbidden).
        """
        # API check
        token_a = RefreshToken.for_user(self.surveyor_a).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token_a}')
        api_resp = self.client.get(f'/api/claims/{self.claim_2.id}/')
        self.assertIn(api_resp.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND])

        # Web direct URL check
        django_client = Client()
        django_client.force_login(self.surveyor_a)
        web_resp = django_client.get(f'/claims/{self.claim_2.id}/')
        self.assertEqual(web_resp.status_code, 403)

        # Symmetric check: Surveyor B cannot view Surveyor A's claim
        token_b = RefreshToken.for_user(self.surveyor_b).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token_b}')
        api_resp_b = self.client.get(f'/api/claims/{self.claim_1.id}/')
        self.assertIn(api_resp_b.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND])

        django_client.force_login(self.surveyor_b)
        web_resp_b = django_client.get(f'/claims/{self.claim_1.id}/')
        self.assertEqual(web_resp_b.status_code, 403)

    def test_surveyor_cannot_access_user_management_or_master_data_endpoints(self):
        """Surveyor is prohibited from modifying master data and accessing user management."""
        token_a = RefreshToken.for_user(self.surveyor_a).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token_a}')

        # 1. Master data creation rejected (403 Forbidden)
        insurer_resp = self.client.post('/api/insurers/', {
            'company_name': 'Unauthorized Insurer',
            'branch_name': 'Unauthorized',
            'address': 'Addr',
            'city': 'City',
            'state': 'State',
            'pincode': '123456',
            'contact_person': 'CP',
            'phone': '1234567890',
            'email': 'unauth@test.com'
        })
        self.assertEqual(insurer_resp.status_code, status.HTTP_403_FORBIDDEN)

        insured_resp = self.client.post('/api/insured/', {
            'name': 'Unauthorized Insured',
            'address': 'Addr',
            'city': 'City',
            'state': 'State',
            'pincode': '123456',
            'phone': '1234567890',
            'email': 'unauth@test.com'
        })
        self.assertEqual(insured_resp.status_code, status.HTTP_403_FORBIDDEN)

        policy_resp = self.client.post('/api/policies/', {
            'insurer': self.insurer.id,
            'policy_number': 'UNAUTH-01',
            'policy_type': 'Fire',
            'start_datetime': timezone.now().isoformat(),
            'end_datetime': (timezone.now() + timezone.timedelta(days=365)).isoformat(),
            'sum_insured': '100000.00'
        })
        self.assertEqual(policy_resp.status_code, status.HTTP_403_FORBIDDEN)

        # 2. Django admin user-management URL blocked
        django_client = Client()
        django_client.force_login(self.surveyor_a)
        admin_user_resp = django_client.get('/admin/accounts/customuser/')
        # Non-staff users get redirected to admin login (302) or 403 Forbidden
        self.assertIn(admin_user_resp.status_code, [302, 403])


class FileSecurityAndValidationTests(BaseWorkflowTestCase):
    """
    Dedicated tests for document/photo file validation and secure download isolation:
    - Allowed file types upload successfully.
    - Disallowed and oversized files are rejected.
    - Direct URL access to another surveyor's media files is blocked (403).
    """

    def setUp(self):
        super().setUp()
        self.doc_type, _ = DocumentType.objects.get_or_create(
            code='GEN_DOC',
            defaults={'name': 'General Document', 'is_active': True}
        )

        # Surveyor B is assigned to Claim 2
        self.claim_b = Claim.objects.create(
            claim_number='CLM-FILE-002',
            survey_type=self.survey_type,
            insurer=self.insurer,
            insured=self.insured,
            policy=self.policy,
            instruction_date=date(2026, 9, 2),
            instruction_source='Email',
            date_of_loss=date(2026, 8, 30),
            nature_of_loss='Water damage',
            loss_location='Godown 2',
            claimed_amount=Decimal('50000.00'),
            status=ClaimStatus.ASSIGNED,
            created_by=self.admin
        )
        SurveyAssignment.objects.create(
            claim=self.claim_b,
            surveyor=self.surveyor_b,
            assigned_by=self.admin,
            due_date=date(2026, 9, 25),
            status=SurveyAssignment.Status.ASSIGNED
        )

        # Files on Claim B
        self.claim_doc_b = ClaimDocument.objects.create(
            claim=self.claim_b,
            document_type=self.doc_type,
            file=make_test_pdf('claim_b_doc.pdf'),
            uploaded_by=self.surveyor_b
        )

        self.inspection_b = Inspection.objects.create(
            claim=self.claim_b,
            surveyor=self.surveyor_b,
            inspection_date=date(2026, 9, 10),
            start_time='10:00',
            end_time='12:00',
            location='Godown 2',
            person_contacted='Godown Supervisor',
            contact_number='+1-555-4003',
            status=Inspection.Status.COMPLETED
        )
        self.photo_b = InspectionPhoto.objects.create(
            inspection=self.inspection_b,
            image=make_test_image('claim_b_photo.jpg'),
            uploaded_by=self.surveyor_b
        )

        self.invoice_b = Invoice.objects.create(
            claim=self.claim_b,
            invoice_number='INV-B-001',
            invoice_date=date(2026, 9, 11),
            vendor_name='Vendor B',
            amount=Decimal('10000.00'),
            total_amount=Decimal('10000.00'),
            document=make_test_pdf('invoice_b_doc.pdf')
        )

    def test_file_type_and_size_validation(self):
        """Allowed file types pass; executable/malicious extensions and >10MB files fail."""
        # Allowed files
        valid_pdf = SimpleUploadedFile("policy.pdf", b"%PDF-1.4 sample content", content_type="application/pdf")
        valid_jpg = make_test_image("inspection.jpg")
        valid_png = SimpleUploadedFile("scheme.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 20, content_type="image/png")

        validate_document_file(valid_pdf)
        validate_document_file(valid_jpg)
        validate_document_file(valid_png)
        validate_image_file(valid_jpg)
        validate_image_file(valid_png)

        # Disallowed executables / scripts
        for bad_ext in ["payload.exe", "script.sh", "install.bat", "module.py"]:
            bad_file = SimpleUploadedFile(bad_ext, b"binary code", content_type="application/octet-stream")
            with self.assertRaises(ValidationError, msg=f"Should reject {bad_ext}"):
                validate_document_file(bad_file)
            with self.assertRaises(ValidationError, msg=f"Should reject {bad_ext}"):
                validate_image_file(bad_file)

        # Oversized file (> 10MB)
        oversized = SimpleUploadedFile("big.pdf", b"X" * (11 * 1024 * 1024), content_type="application/pdf")
        with self.assertRaises(ValidationError):
            validate_file_size(oversized)

    def test_cross_surveyor_file_download_isolation(self):
        """
        Surveyor A cannot download Claim B's documents, photos, or invoices
        even by guessing or navigating directly to the media URL.
        """
        django_client = Client()

        # 1. Surveyor A (unassigned to Claim B) gets 403 Forbidden
        django_client.force_login(self.surveyor_a)
        resp_doc = django_client.get(f'/media/{self.claim_doc_b.file.name}')
        self.assertEqual(resp_doc.status_code, 403)

        resp_photo = django_client.get(f'/media/{self.photo_b.image.name}')
        self.assertEqual(resp_photo.status_code, 403)

        resp_inv = django_client.get(f'/media/{self.invoice_b.document.name}')
        self.assertEqual(resp_inv.status_code, 403)

        # 2. Surveyor B (assigned to Claim B) gets 200 OK
        django_client.force_login(self.surveyor_b)
        resp_b_doc = django_client.get(f'/media/{self.claim_doc_b.file.name}')
        self.assertEqual(resp_b_doc.status_code, 200)

        # 3. Admin gets 200 OK
        django_client.force_login(self.admin)
        resp_admin_doc = django_client.get(f'/media/{self.claim_doc_b.file.name}')
        self.assertEqual(resp_admin_doc.status_code, 200)

        # 4. Anonymous user gets redirected to login (302)
        django_client.logout()
        resp_anon = django_client.get(f'/media/{self.claim_doc_b.file.name}')
        self.assertEqual(resp_anon.status_code, 302)
        self.assertIn('/login/', resp_anon.url)


class SkipAheadAndReportSubmittedVisibilityTests(BaseWorkflowTestCase):
    """
    Test suite for:
    1. Mandatory justification guard when skipping LOR/Assessment for ISR/FSR.
    2. Visibility of latest submitted report stage (ILA/ISR/FSR) on REPORT_SUBMITTED.
    3. In Progress filter including REPORT_SUBMITTED claims.
    """

    def setUp(self):
        super().setUp()
        self.client = Client()
        self.client.force_login(self.admin)
        # Advance claim to INSPECTION_COMPLETED
        transition_claim_status(self.claim, ClaimStatus.ASSIGNED, self.admin, remarks="Assigned")
        transition_claim_status(self.claim, ClaimStatus.INSPECTION_PENDING, self.admin, remarks="Pending")
        transition_claim_status(self.claim, ClaimStatus.INSPECTION_COMPLETED, self.admin, remarks="Completed")

    def test_skip_ahead_to_isr_without_reason_rejected(self):
        """Transition from INSPECTION_COMPLETED directly to ISR_PREPARED without remarks must be rejected."""
        with self.assertRaises(ValidationError) as ctx:
            transition_claim_status(self.claim, ClaimStatus.ISR_PREPARED, self.admin, remarks="")
        self.assertIn("Justification is required", str(ctx.exception))
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, ClaimStatus.INSPECTION_COMPLETED)

    def test_skip_ahead_to_isr_with_reason_succeeds(self):
        """Transition from INSPECTION_COMPLETED to ISR_PREPARED with remarks succeeds and records remarks."""
        transition_claim_status(
            self.claim,
            ClaimStatus.ISR_PREPARED,
            self.admin,
            remarks="Direct ISR approved by senior underwriter"
        )
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, ClaimStatus.ISR_PREPARED)
        latest_history = ClaimStatusHistory.objects.filter(claim=self.claim).latest('changed_at')
        self.assertEqual(latest_history.remarks, "Direct ISR approved by senior underwriter")

    def test_skip_ahead_to_fsr_without_reason_rejected(self):
        """Transition directly to FSR_PREPARED without LOR/Assessment and without remarks must be rejected."""
        with self.assertRaises(ValidationError) as ctx:
            transition_claim_status(self.claim, ClaimStatus.FSR_PREPARED, self.admin, remarks="")
        self.assertIn("Justification is required", str(ctx.exception))

    def test_sequential_transition_without_reason_succeeds(self):
        """Claims that have passed through both LOR_ISSUED and ASSESSMENT_IN_PROGRESS do not require remarks."""
        transition_claim_status(self.claim, ClaimStatus.LOR_ISSUED, self.admin, remarks="LOR Issued")
        transition_claim_status(self.claim, ClaimStatus.ASSESSMENT_IN_PROGRESS, self.admin, remarks="Assessment")
        self.assertTrue(self.claim.has_completed_lor_and_assessment)

        # Transition to ISR_PREPARED with empty remarks must succeed
        transition_claim_status(self.claim, ClaimStatus.ISR_PREPARED, self.admin, remarks="")
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, ClaimStatus.ISR_PREPARED)

    def test_report_submitted_stage_visibility(self):
        """REPORT_SUBMITTED status pill shows the exact stage of the latest submitted report."""
        from reports.models import ILA, ReportStatus
        # Claim transitions via ILA_PREPARED to REPORT_SUBMITTED
        transition_claim_status(self.claim, ClaimStatus.ILA_PREPARED, self.admin, remarks="ILA prepared")
        transition_claim_status(self.claim, ClaimStatus.REPORT_SUBMITTED, self.admin, remarks="Report submitted")
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status_display_with_stage, "Report Submitted")

        # Create submitted ILA
        import datetime
        ila = ILA.objects.create(
            claim=self.claim,
            report_number="SSLA-91-F-P-269999",
            report_date=timezone.localdate(),
            instruction_date=timezone.localdate(),
            instruction_source="Email",
            surveyor=self.surveyor_a,
            visit_date=timezone.localdate(),
            visit_start_time=datetime.time(10, 0),
            visit_end_time=datetime.time(12, 0),
            inspection_location="Site 1",
            person_contacted="Site Rep",
            contact_number="9999999999",
            policy_number="POL-123",
            policy_type="Fire",
            commodity="Stock",
            sum_insured=Decimal("100000.00"),
            policy_excess=Decimal("1000.00"),
            survey_and_inspection="Inspection details",
            extent_of_damage="Extensive water damage",
            cause_of_damage="Pipe burst",
            salvage_prospect="Partial salvage possible",
            estimated_loss=Decimal("50000.00"),
            claimed_amount=Decimal("60000.00"),
            policy_liability="Covered under standard policy",
            budgetary_reserve=Decimal("45000.00"),
            status=ReportStatus.SUBMITTED,
            prepared_by=self.surveyor_a,
            submitted_at=timezone.now()
        )
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.latest_submitted_report_type, "ILA")
        self.assertEqual(self.claim.status_display_with_stage, "Report Submitted (ILA)")

    def test_in_progress_filter_includes_report_submitted(self):
        """filter=in_progress includes claims in REPORT_SUBMITTED status."""
        transition_claim_status(self.claim, ClaimStatus.ILA_PREPARED, self.admin, remarks="ILA prepared")
        transition_claim_status(self.claim, ClaimStatus.REPORT_SUBMITTED, self.admin, remarks="Report submitted")
        self.claim.refresh_from_db()

        response = self.client.get('/claims/?filter=in_progress')
        self.assertEqual(response.status_code, 200)
        claims_in_page = response.context['page_obj'].object_list
        self.assertIn(self.claim, claims_in_page)



class ClaimApproveAndCloseTests(BaseWorkflowTestCase):
    """
    Tests for the web-portal 'Approve & Close Claim' action.

    Covers:
      - Admin approval from REPORT_SUBMITTED, FSR_PREPARED, RESUBMITTED.
      - Surveyor access denied (403).
      - Blank remarks rejected.
      - Defensive: no submitted report -> fail gracefully.
      - Report status becomes FINAL after close.
      - Skip-ahead path: INSPECTION_COMPLETED -> FSR_PREPARED (no ILA); FSR template
        renders instruction_date / instruction_source from claim fields, not blank.
    """

    def _make_fsr_submitted(self):
        """Push self.claim to FSR_PREPARED with a SUBMITTED FSR report."""
        Claim.objects.filter(pk=self.claim.pk).update(status=ClaimStatus.FSR_PREPARED)
        self.claim.refresh_from_db()
        return FSR.objects.create(
            claim=self.claim,
            report_number="FSR-TEST-001",
            report_date=timezone.localdate(),
            value_at_risk=Decimal("400000.00"),
            sum_insured=Decimal("500000.00"),
            introduction="Test FSR intro",
            occurrence_details="Electrical short circuit in Panel A",
            survey_details="Site visit conducted",
            extent_of_loss="Moderate damage to electrical panel",
            cause_of_loss="Electrical short circuit",
            admissibility="Admissible",
            policy_coverage="Covered",
            policy_exclusions="None applicable",
            final_opinion="Claim is admissible; loss well-documented",
            status=ReportStatus.SUBMITTED,
            prepared_by=self.surveyor_a,
            submitted_at=timezone.now(),
        )

    def _make_ila_submitted(self):
        """Push self.claim to REPORT_SUBMITTED with a SUBMITTED ILA."""
        import datetime as dt
        Claim.objects.filter(pk=self.claim.pk).update(status=ClaimStatus.REPORT_SUBMITTED)
        self.claim.refresh_from_db()
        return ILA.objects.create(
            claim=self.claim,
            report_number="ILA-TEST-001",
            report_date=timezone.localdate(),
            instruction_date=timezone.localdate(),
            instruction_source="Email from insurer",
            surveyor=self.surveyor_a,
            visit_date=timezone.localdate(),
            visit_start_time=dt.time(9, 0),
            visit_end_time=dt.time(11, 0),
            inspection_location="Site 1",
            person_contacted="John Site",
            contact_number="9000000000",
            policy_number="POL-WF-2026-001",
            policy_type="Fire",
            commodity="Stocks",
            sum_insured=Decimal("500000.00"),
            policy_excess=Decimal("5000.00"),
            survey_and_inspection="Detailed inspection done",
            extent_of_damage="Fire damage to electrical systems",
            cause_of_damage="Short circuit",
            salvage_prospect="Minor",
            estimated_loss=Decimal("100000.00"),
            claimed_amount=Decimal("120000.00"),
            policy_liability="Covered",
            budgetary_reserve=Decimal("95000.00"),
            status=ReportStatus.SUBMITTED,
            prepared_by=self.surveyor_a,
            submitted_at=timezone.now(),
        )

    def test_admin_can_approve_and_close_from_report_submitted(self):
        """Admin POST with valid remarks closes a claim that has a SUBMITTED ILA."""
        self._make_ila_submitted()
        self.client.force_login(self.admin)
        response = self.client.post(
            f"/claims/{self.claim.pk}/approve-and-close/",
            {"remarks": "All documents reviewed; claim approved for settlement."},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, ClaimStatus.CLOSED)

    def test_admin_can_approve_and_close_from_fsr_prepared(self):
        """Admin POST with valid remarks closes a claim that has a SUBMITTED FSR."""
        self._make_fsr_submitted()
        self.client.force_login(self.admin)
        response = self.client.post(
            f"/claims/{self.claim.pk}/approve-and-close/",
            {"remarks": "FSR reviewed and approved. Closing claim."},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, ClaimStatus.CLOSED)

    def test_admin_can_approve_and_close_from_resubmitted(self):
        """Admin closes a RESUBMITTED claim that has a SUBMITTED FSR."""
        self._make_fsr_submitted()
        # Put claim into RESUBMITTED (FSR still SUBMITTED)
        Claim.objects.filter(pk=self.claim.pk).update(status=ClaimStatus.RESUBMITTED)
        self.claim.refresh_from_db()
        self.client.force_login(self.admin)
        response = self.client.post(
            f"/claims/{self.claim.pk}/approve-and-close/",
            {"remarks": "Resubmission accepted; closing."},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, ClaimStatus.CLOSED)

    def test_surveyor_cannot_approve_and_close(self):
        """Surveyor gets 403 when attempting approve-and-close."""
        self._make_fsr_submitted()
        self.client.force_login(self.surveyor_a)
        response = self.client.post(
            f"/claims/{self.claim.pk}/approve-and-close/",
            {"remarks": "Trying to close as surveyor"},
        )
        self.assertEqual(response.status_code, 403)
        self.claim.refresh_from_db()
        self.assertNotEqual(self.claim.status, ClaimStatus.CLOSED)

    def test_blank_remarks_rejected(self):
        """POST with whitespace-only remarks redirects back without closing."""
        self._make_fsr_submitted()
        self.client.force_login(self.admin)
        response = self.client.post(
            f"/claims/{self.claim.pk}/approve-and-close/",
            {"remarks": "   "},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.claim.refresh_from_db()
        self.assertNotEqual(self.claim.status, ClaimStatus.CLOSED)
        msgs = [m.message for m in response.context["messages"]]
        self.assertTrue(any("remarks" in m.lower() for m in msgs))

    def test_no_submitted_report_blocked(self):
        """When no submitted report exists, approve-and-close fails gracefully."""
        Claim.objects.filter(pk=self.claim.pk).update(status=ClaimStatus.FSR_PREPARED)
        self.claim.refresh_from_db()
        # No report created
        self.client.force_login(self.admin)
        response = self.client.post(
            f"/claims/{self.claim.pk}/approve-and-close/",
            {"remarks": "Attempting close with no report"},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.claim.refresh_from_db()
        self.assertNotEqual(self.claim.status, ClaimStatus.CLOSED)
        msgs = [m.message for m in response.context["messages"]]
        self.assertTrue(any("no submitted report" in m.lower() for m in msgs))

    def test_report_status_becomes_final_after_close(self):
        """The submitted FSR must be marked FINAL after approve-and-close."""
        fsr = self._make_fsr_submitted()
        self.client.force_login(self.admin)
        self.client.post(
            f"/claims/{self.claim.pk}/approve-and-close/",
            {"remarks": "Approved. Closing claim."},
            follow=True,
        )
        fsr.refresh_from_db()
        self.assertEqual(fsr.status, ReportStatus.FINAL)

    def test_skip_ahead_fsr_instruction_details_not_blank(self):
        """
        Skip-ahead path: INSPECTION_COMPLETED -> FSR_PREPARED (no ILA ever created).
        The FSR PDF template must render instruction_date / instruction_source from
        claim fields without raising an exception and without blank output.
        """
        # Direct DB update: NEW -> INSPECTION_COMPLETED is not a single-hop allowed
        # transition in ALLOWED_TRANSITIONS, so bypass the service guard to put the
        # claim into the skip-ahead starting state.
        Claim.objects.filter(pk=self.claim.pk).update(status=ClaimStatus.INSPECTION_COMPLETED)
        self.claim.refresh_from_db()
        # Transition to FSR_PREPARED with justification remarks (skip-ahead path)
        transition_claim_status(
            self.claim, ClaimStatus.FSR_PREPARED, self.admin,
            remarks="Skipping ILA; proceeding directly to FSR as agreed with underwriter"
        )
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, ClaimStatus.FSR_PREPARED)
        # No ILA reports must exist (none created throughout)
        self.assertFalse(self.claim.ila_reports.exists())

        # Claim instruction fields must be populated (set in BaseWorkflowTestCase.setUp)
        self.assertIsNotNone(self.claim.instruction_date)
        self.assertTrue(bool(str(self.claim.instruction_source).strip()))

        # Render FSR template - must not raise
        from reports.services import get_soteria_assets
        from django.template.loader import render_to_string
        ctx = get_soteria_assets()
        ctx["claim"] = self.claim
        try:
            html = render_to_string("reports/fsr_pdf.html", ctx)
        except Exception as exc:
            self.fail(f"FSR template raised for skip-ahead claim: {exc}")

        # instruction_source value must appear in rendered output
        self.assertIn(self.claim.instruction_source, html)
