from datetime import date, time
from decimal import Decimal
from io import BytesIO
from PIL import Image

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from surveys.models import (
    SurveyType,
    Inspection,
    InspectionPhoto,
    InspectionObservation,
    FireClaimDetails,
    EngineeringClaimDetails,
)
from claims.models import (
    Insurer,
    Insured,
    Policy,
    Claim,
    ClaimStatus,
    SurveyAssignment,
    Priority,
)
from documents.models import DocumentType, ClaimDocument, Requirement
from assessments.models import Assessment, AssessmentItem
from reports.models import FSR, ReportStatus

User = get_user_model()


def generate_test_image(filename="test_photo.jpg", image_format="JPEG"):
    """Generate in-memory test image."""
    stream = BytesIO()
    image = Image.new("RGB", (100, 100), color=(0, 128, 255))
    image.save(stream, format=image_format)
    stream.seek(0)
    return SimpleUploadedFile(filename, stream.read(), content_type=f"image/{image_format.lower()}")


def generate_test_pdf(filename="test_doc.pdf"):
    """Generate in-memory dummy PDF file."""
    content = b"%PDF-1.4 test document content %%EOF"
    return SimpleUploadedFile(filename, content, content_type="application/pdf")


class HTMLFormsBaseTestCase(TestCase):
    def setUp(self):
        self.client = Client()

        # Users
        self.admin = User.objects.create_user(
            username='admin_user',
            email='admin@survey.test',
            password='password123',
            role=User.Role.ADMIN
        )
        self.surveyor = User.objects.create_user(
            username='surveyor_user',
            email='surveyor@survey.test',
            password='password123',
            role=User.Role.SURVEYOR
        )
        self.unassigned_surveyor = User.objects.create_user(
            username='other_surveyor',
            email='other@survey.test',
            password='password123',
            role=User.Role.SURVEYOR
        )

        # Survey Types
        self.st_fire = SurveyType.objects.get(code='FIRE')
        self.st_eng = SurveyType.objects.get(code='ENG')

        # Insurer & Insured
        self.insurer = Insurer.objects.create(
            company_name='Apex General Insurance',
            branch_name='North Branch',
            contact_person='Alice Admin',
            phone='+1-555-1111',
            email='claims@apexgen.com',
            address='123 Wall St',
            city='Finance City',
            state='State',
            pincode='100001'
        )
        self.insured = Insured.objects.create(
            name='Standard Manufacturing Co',
            company_name='Standard Mfg Ltd',
            contact_person='Bob Builder',
            phone='+1-555-2222',
            email='contact@standardmfg.com',
            address='Industrial Estate Plot 4',
            city='Metro City',
            state='State',
            pincode='200001'
        )

        # Policy
        now = timezone.now()
        self.policy = Policy.objects.create(
            insurer=self.insurer,
            policy_number='POL-FIRE-2026-001',
            policy_type='Standard Fire & Special Perils',
            start_datetime=now - timezone.timedelta(days=30),
            end_datetime=now + timezone.timedelta(days=335),
            sum_insured=Decimal('2000000.00'),
            excess=Decimal('10000.00'),
            commodity='Factory Plant & Machinery',
            subject_matter='Factory shed and processing equipment'
        )

        # Sample claim assigned to self.surveyor
        self.claim = Claim.objects.create(
            claim_number='CLM-TEST-001',
            survey_type=self.st_fire,
            insurer=self.insurer,
            insured=self.insured,
            policy=self.policy,
            instruction_date=date(2026, 9, 10),
            instruction_source='Email Instruction',
            date_of_loss=date(2026, 9, 8),
            nature_of_loss='Fire outbreak in main electrical room',
            loss_location='Plot 4 Industrial Estate',
            claimed_amount=Decimal('500000.00'),
            status=ClaimStatus.ASSIGNED,
            created_by=self.admin
        )

        self.assignment = SurveyAssignment.objects.create(
            claim=self.claim,
            surveyor=self.surveyor,
            assigned_by=self.admin,
            due_date=date(2026, 9, 20),
            status=SurveyAssignment.Status.ASSIGNED
        )


class ClaimWizardHTMLTests(HTMLFormsBaseTestCase):
    def test_claim_create_permissions(self):
        # Unauthenticated -> redirect to login
        response = self.client.get('/claims/create/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

        # Surveyor -> 403 Forbidden
        self.client.force_login(self.surveyor)
        response = self.client.get('/claims/create/')
        self.assertEqual(response.status_code, 403)

        # Admin -> 200 OK
        self.client.force_login(self.admin)
        response = self.client.get('/claims/create/')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'claims/claim_form.html')

    def test_claim_create_with_fire_details(self):
        self.client.force_login(self.admin)
        post_data = {
            'claim_number': 'CLM-WIZARD-FIRE',
            'report_number': 'REP-FIRE-001',
            'survey_type': self.st_fire.id,
            'instruction_date': '2026-09-15',
            'instruction_source': 'Underwriting Branch',
            'priority': Priority.HIGH,
            'insurer': self.insurer.id,
            'insured': self.insured.id,
            'policy': self.policy.id,
            'date_of_loss': '2026-09-14',
            'nature_of_loss': 'Fire in storage warehouse',
            'loss_location': 'Warehouse 3, Industrial Area',
            'claimed_amount': '250000.00',
            'claim_description': 'Major damage to storage boxes and wiring',
            'contact_person': 'Site Manager Dave',
            'contact_phone': '+1-555-4444',
            'contact_email': 'dave@mfg.com',
            # Fire detail fields
            'construction_details': 'Class 1 RCC Framing',
            'occupancy': 'Storage & Logistics',
            'building_description': 'Single-story prefabricated metal shed',
            'fire_cause': 'Electrical short-circuit in ceiling conduit',
            'point_of_origin': 'Ceiling junction box near Bay 2',
        }

        response = self.client.post('/claims/create/', data=post_data, follow=True)
        self.assertEqual(response.status_code, 200)

        # Verify Claim created
        claim = Claim.objects.get(claim_number='CLM-WIZARD-FIRE')
        self.assertEqual(claim.survey_type, self.st_fire)
        self.assertEqual(claim.created_by, self.admin)
        self.assertEqual(claim.status, ClaimStatus.NEW)

        # Verify FireClaimDetails created
        self.assertTrue(FireClaimDetails.objects.filter(claim=claim).exists())
        fire_details = FireClaimDetails.objects.get(claim=claim)
        self.assertEqual(fire_details.construction_details, 'Class 1 RCC Framing')
        self.assertEqual(fire_details.point_of_origin, 'Ceiling junction box near Bay 2')

        # Verify EngineeringClaimDetails NOT created
        self.assertFalse(EngineeringClaimDetails.objects.filter(claim=claim).exists())

    def test_claim_create_without_survey_details_browser_format(self):
        """Verify that registering a new claim with empty survey details succeeds (survey details optional at registration)."""
        self.client.force_login(self.admin)
        post_data = {
            'claim_number': 'CLM-BROWSER-EMPTY',
            'report_number': 'REP-EMPTY-001',
            'survey_type': self.st_fire.id,
            'instruction_date': '2026-09-15',
            'instruction_source': 'Underwriting Branch',
            'priority': Priority.MEDIUM,
            'insurer': self.insurer.id,
            'insured': self.insured.id,
            'policy': self.policy.id,
            'date_of_loss': '2026-09-14',
            'nature_of_loss': 'Fire in storage warehouse',
            'loss_location': 'Warehouse 3, Industrial Area',
            'fire-occupancy': '',
            'fire-construction_details': '',
            'fire-building_description': '',
        }
        response = self.client.post('/claims/create/', data=post_data, follow=True)
        self.assertEqual(response.status_code, 200)

        claim = Claim.objects.get(claim_number='CLM-BROWSER-EMPTY')
        self.assertEqual(claim.status, ClaimStatus.NEW)
        self.assertIsNone(claim.get_survey_details())

    def test_claim_create_with_prefixed_fire_details_browser_format(self):
        """Verify that browser submissions with 'fire-' prefixed fields successfully save FireClaimDetails."""
        self.client.force_login(self.admin)
        post_data = {
            'claim_number': 'CLM-BROWSER-FIRE',
            'report_number': 'REP-FIRE-002',
            'survey_type': self.st_fire.id,
            'instruction_date': '2026-09-15',
            'instruction_source': 'Underwriting Branch',
            'priority': Priority.HIGH,
            'insurer': self.insurer.id,
            'insured': self.insured.id,
            'policy': self.policy.id,
            'date_of_loss': '2026-09-14',
            'nature_of_loss': 'Fire in storage warehouse',
            'loss_location': 'Warehouse 3, Industrial Area',
            'fire-occupancy': 'Textile Warehouse',
            'fire-construction_details': 'Class 1 RCC Framing',
            'fire-building_description': 'Metal shed structure',
            'fire-point_of_origin': 'Main electric room',
        }
        response = self.client.post('/claims/create/', data=post_data, follow=True)
        self.assertEqual(response.status_code, 200)

        claim = Claim.objects.get(claim_number='CLM-BROWSER-FIRE')
        fire_details = FireClaimDetails.objects.get(claim=claim)
        self.assertEqual(fire_details.occupancy, 'Textile Warehouse')
        self.assertEqual(fire_details.construction_details, 'Class 1 RCC Framing')

    def test_claim_create_with_incomplete_details_shows_errors(self):
        """Verify that partial survey details submission returns form with errors displayed."""
        self.client.force_login(self.admin)
        post_data = {
            'claim_number': 'CLM-BROWSER-INCOMPLETE',
            'survey_type': self.st_fire.id,
            'instruction_date': '2026-09-15',
            'instruction_source': 'Underwriting Branch',
            'priority': Priority.HIGH,
            'insurer': self.insurer.id,
            'insured': self.insured.id,
            'policy': self.policy.id,
            'date_of_loss': '2026-09-14',
            'nature_of_loss': 'Fire in warehouse',
            'loss_location': 'Industrial Area',
            'fire-occupancy': 'Textile Warehouse',
            'fire-construction_details': '',  # missing required field
            'fire-building_description': '',  # missing required field
        }
        response = self.client.post('/claims/create/', data=post_data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Please resolve the following errors")
        self.assertContains(response, "Construction Details")
        self.assertFalse(Claim.objects.filter(claim_number='CLM-BROWSER-INCOMPLETE').exists())


class InspectionFormHTMLTests(HTMLFormsBaseTestCase):
    def test_surveyor_saves_inspection_with_observations_and_files(self):
        self.client.force_login(self.surveyor)

        photo1 = generate_test_image('damage_photo.jpg')
        doc1 = generate_test_pdf('police_report.pdf')

        post_data = {
            'inspection_date': '2026-09-12',
            'start_time': '10:00',
            'end_time': '12:30',
            'location': 'Plot 4 Main Plant',
            'person_contacted': 'Plant Officer Dan',
            'contact_number': '+1-555-7890',
            'contact_email': 'dan@plant.com',
            'site_representative': 'Dan and Bob',
            'observations': 'Comprehensive physical inspection conducted across electrical panel room.',
            'status': Inspection.Status.COMPLETED,
            'extent_of_damage': 'Main breaker panel completely charred.',
            'cause_observations': 'Overheating observed in cable terminations.',
            'salvage_observations': 'Copper busbars can be salvaged.',
            'photos': [photo1],
            'documents': [doc1],
        }

        response = self.client.post(
            f'/claims/{self.claim.id}/inspection/save/',
            data=post_data,
            follow=True
        )
        self.assertEqual(response.status_code, 200)

        # Verify Inspection
        inspection = Inspection.objects.get(claim=self.claim)
        self.assertEqual(inspection.surveyor, self.surveyor)
        self.assertEqual(inspection.status, Inspection.Status.COMPLETED)
        self.assertEqual(inspection.person_contacted, 'Plant Officer Dan')

        # Verify direct observation fields on Inspection
        self.assertEqual(inspection.extent_of_damage, 'Main breaker panel completely charred.')
        self.assertEqual(inspection.cause_observations, 'Overheating observed in cable terminations.')
        self.assertEqual(inspection.salvage_observations, 'Copper busbars can be salvaged.')

        # Verify NO InspectionObservation rows were created
        self.assertEqual(InspectionObservation.objects.filter(inspection=inspection).count(), 0)

        # Verify Photos & Documents
        self.assertEqual(InspectionPhoto.objects.filter(inspection=inspection).count(), 1)
        self.assertEqual(ClaimDocument.objects.filter(claim=self.claim).count(), 1)

        # Verify claim status transitioned to INSPECTION_COMPLETED
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, ClaimStatus.INSPECTION_COMPLETED)

    def test_admin_cannot_submit_inspection(self):
        self.client.force_login(self.admin)
        post_data = {
            'inspection_date': '2026-09-12',
            'start_time': '10:00',
            'end_time': '11:00',
            'location': 'Site A',
            'status': Inspection.Status.SCHEDULED,
        }
        response = self.client.post(f'/claims/{self.claim.id}/inspection/save/', data=post_data)
        # @surveyor_required raises PermissionDenied (403)
        self.assertEqual(response.status_code, 403)

    def test_unassigned_surveyor_cannot_submit_inspection(self):
        self.client.force_login(self.unassigned_surveyor)
        post_data = {
            'inspection_date': '2026-09-12',
            'start_time': '10:00',
            'end_time': '11:00',
            'location': 'Site A',
            'status': Inspection.Status.SCHEDULED,
        }
        response = self.client.post(f'/claims/{self.claim.id}/inspection/save/', data=post_data)
        self.assertEqual(response.status_code, 403)


class LORFormHTMLTests(HTMLFormsBaseTestCase):
    def test_surveyor_adds_lor_requirement_and_updates_status(self):
        self.client.force_login(self.surveyor)
        # Set claim to ILA_PREPARED to test status transition
        self.claim.status = ClaimStatus.ILA_PREPARED
        self.claim.save()

        # 1. Add requirement
        post_data = {
            'description': 'Fire department attendance certificate & incident diary',
            'requested_from': Requirement.RequestedFrom.INSURED,
            'requested_date': '2026-09-12',
            'due_date': '2026-09-19',
            'status': Requirement.Status.PENDING,
            'remarks': 'Urgent for cause verification',
        }
        response = self.client.post(f'/claims/{self.claim.id}/lor/add/', data=post_data, follow=True)
        self.assertEqual(response.status_code, 200)

        req = Requirement.objects.get(claim=self.claim)
        self.assertEqual(req.description, 'Fire department attendance certificate & incident diary')
        self.assertEqual(req.status, Requirement.Status.PENDING)

        # Claim status should advance to LOR_ISSUED
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, ClaimStatus.LOR_ISSUED)

        # 2. Update requirement status as surveyor (e.g. RECEIVED)
        update_data = {'status': Requirement.Status.RECEIVED}
        response = self.client.post(
            f'/claims/{self.claim.id}/lor/{req.id}/update-status/',
            data=update_data,
            follow=True
        )
        self.assertEqual(response.status_code, 200)

        req.refresh_from_db()
        self.assertEqual(req.status, Requirement.Status.RECEIVED)
        self.assertIsNotNone(req.received_date)

        # 3. Only Admin can set verification status to VERIFIED
        self.client.force_login(self.admin)
        response = self.client.post(
            f'/claims/{self.claim.id}/lor/{req.id}/update-status/',
            data={'status': Requirement.Status.VERIFIED},
            follow=True
        )
        self.assertEqual(response.status_code, 200)
        req.refresh_from_db()
        self.assertEqual(req.status, Requirement.Status.VERIFIED)


class AssessmentFormHTMLTests(HTMLFormsBaseTestCase):
    def test_surveyor_item_and_financial_recalculation(self):
        self.client.force_login(self.surveyor)

        # 1. Add an assessment item
        item_data = {
            'description': 'Replacement MCCB breaker unit',
            'category': 'Parts',
            'quantity': '4',
            'rate': '25000.00',
            'claimed_amount': '120000.00',
        }
        response = self.client.post(
            f'/claims/{self.claim.id}/assessment/item/add/',
            data=item_data,
            follow=True
        )
        self.assertEqual(response.status_code, 200)

        assessment = Assessment.objects.get(claim=self.claim)
        self.assertEqual(assessment.items.count(), 1)
        item = assessment.items.first()
        self.assertEqual(item.assessed_amount, Decimal('100000.00')) # 4 * 25000
        self.assertEqual(assessment.gross_assessed_loss, Decimal('100000.00'))

        # 2. Save financial deductions
        # salvage=10000, underinsurance=10% (10000 - 1000 = 9000 off remaining 90000),
        # excess=5000 -> recalculate_assessment checks
        fin_data = {
            'salvage_amount': '10000.00',
            'underinsurance_percentage': '10.00',
            'depreciation_amount': '5000.00',
            'policy_excess': '5000.00',
            'other_deductions': '0.00',
            'assessment_remarks': 'Standard depreciation and salvage adjustment applied.',
        }
        response = self.client.post(
            f'/claims/{self.claim.id}/assessment/save/',
            data=fin_data,
            follow=True
        )
        self.assertEqual(response.status_code, 200)

        assessment.refresh_from_db()
        self.assertEqual(assessment.salvage_amount, Decimal('10000.00'))
        self.assertEqual(assessment.depreciation_amount, Decimal('5000.00'))
        # gross = 100000, underinsurance 10% on gross = 10000
        # salvage = 10000, depreciation = 5000
        # adjusted = 100000 - 10000 - 10000 - 5000 = 75000.00
        # less excess 5000 = net 70000.00
        self.assertEqual(assessment.adjusted_loss, Decimal('75000.00'))
        self.assertEqual(assessment.net_assessed_loss, Decimal('70000.00'))

        # 3. Delete assessment item
        response = self.client.post(
            f'/claims/{self.claim.id}/assessment/item/{item.id}/delete/',
            follow=True
        )
        self.assertEqual(response.status_code, 200)
        assessment.refresh_from_db()
        self.assertEqual(assessment.items.count(), 0)
        self.assertEqual(assessment.gross_assessed_loss, Decimal('0.00'))
        self.assertEqual(assessment.net_assessed_loss, Decimal('0.00'))

    def test_surveyor_item_edit_and_recalculation(self):
        self.client.force_login(self.surveyor)

        # 1. Add item
        item_data = {
            'description': 'Transformer coil replacement',
            'category': 'Parts',
            'specification': '100kVA copper',
            'quantity': '2',
            'rate': '50000.00',
            'claimed_amount': '120000.00',
            'remarks': 'Original estimate',
        }
        self.client.post(
            f'/claims/{self.claim.id}/assessment/item/add/',
            data=item_data,
            follow=True
        )
        assessment = Assessment.objects.get(claim=self.claim)
        item = assessment.items.first()
        self.assertEqual(item.assessed_amount, Decimal('100000.00'))
        self.assertEqual(assessment.gross_assessed_loss, Decimal('100000.00'))

        # 2. Edit item (increase quantity to 3, change rate to 60000)
        edit_data = {
            'description': 'Transformer coil replacement (heavy duty)',
            'category': 'Parts',
            'specification': '125kVA copper',
            'quantity': '3',
            'rate': '60000.00',
            'claimed_amount': '200000.00',
            'remarks': 'Upgraded spec per manufacturer recommendation',
        }
        response = self.client.post(
            f'/claims/{self.claim.id}/assessment/item/{item.id}/edit/',
            data=edit_data,
            follow=True
        )
        self.assertEqual(response.status_code, 200)

        item.refresh_from_db()
        self.assertEqual(item.description, 'Transformer coil replacement (heavy duty)')
        self.assertEqual(item.quantity, Decimal('3.00'))
        self.assertEqual(item.rate, Decimal('60000.00'))
        self.assertEqual(item.assessed_amount, Decimal('180000.00'))

        assessment.refresh_from_db()
        self.assertEqual(assessment.gross_assessed_loss, Decimal('180000.00'))
        self.assertContains(response, 'Transformer coil replacement (heavy duty)')



class ReportLifecycleHTMLTests(HTMLFormsBaseTestCase):
    def setUp(self):
        super().setUp()
        self.claim.status = ClaimStatus.ISR_PREPARED
        self.claim.save()
        from claims.models import ClaimStatusHistory
        ClaimStatusHistory.objects.create(
            claim=self.claim,
            old_status=ClaimStatus.INSPECTION_COMPLETED,
            new_status=ClaimStatus.LOR_ISSUED,
            changed_by=self.surveyor
        )
        ClaimStatusHistory.objects.create(
            claim=self.claim,
            old_status=ClaimStatus.LOR_ISSUED,
            new_status=ClaimStatus.ASSESSMENT_IN_PROGRESS,
            changed_by=self.surveyor
        )
        self.assessment = Assessment.objects.create(
            claim=self.claim,
            gross_assessed_loss=Decimal('100000.00'),
            net_assessed_loss=Decimal('90000.00'),
            created_by=self.surveyor
        )

    def test_fsr_draft_save_preview_generate_and_submit(self):
        self.client.force_login(self.surveyor)

        # 1. Save FSR Draft
        report_data = {
            'report_number': 'FSR-2026-001',
            'report_date': '2026-09-18',
            'introduction': 'Final survey inspection conducted upon request.',
            'occurrence_details': 'Electrical fire destroyed control systems.',
            'survey_details': 'Survey held on site on Sep 12.',
            'extent_of_loss': 'Complete burnout of control cabinet.',
            'cause_of_loss': 'Electrical arcing.',
            'value_at_risk': '2000000.00',
            'sum_insured': '2000000.00',
            'underinsurance_percentage': '0.00',
            'salvage_description': 'Scrap metal',
            'salvage_amount': '5000.00',
            'insured_claim_description': 'Original claim for full panel replacement.',
            'admissibility': 'Admissible under fire peril.',
            'policy_coverage': 'Full coverage in place.',
            'policy_exclusions': 'None triggered.',
            'final_opinion': 'Claim assessed fairly subject to insurer approval.',
        }
        response = self.client.post(
            f'/claims/{self.claim.id}/report/fsr/save/',
            data=report_data,
            follow=True
        )
        self.assertEqual(response.status_code, 200)

        report = FSR.objects.get(claim=self.claim)
        self.assertEqual(report.status, ReportStatus.DRAFT)
        self.assertEqual(report.report_number, 'FSR-2026-001')

        # 2. Preview PDF
        response = self.client.get(f'/claims/{self.claim.id}/report/fsr/preview/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertTrue(len(response.content) > 0)

        # 3. Generate PDF ClaimDocument
        response = self.client.post(
            f'/claims/{self.claim.id}/report/fsr/generate-pdf/',
            follow=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(ClaimDocument.objects.filter(claim=self.claim).exists())

        # 4. Submit Report
        response = self.client.post(
            f'/claims/{self.claim.id}/report/fsr/submit/',
            follow=True
        )
        self.assertEqual(response.status_code, 200)

        report.refresh_from_db()
        self.claim.refresh_from_db()
        self.assertEqual(report.status, ReportStatus.SUBMITTED)
        self.assertEqual(self.claim.status, ClaimStatus.REPORT_SUBMITTED)

        # 5. Cannot submit already submitted report
        response = self.client.post(
            f'/claims/{self.claim.id}/report/fsr/submit/',
            follow=True
        )
        self.assertEqual(response.status_code, 200)
        # Report status remains SUBMITTED
        report.refresh_from_db()
        self.assertEqual(report.status, ReportStatus.SUBMITTED)


class RoleInterfaceEnforcementHTMLTests(HTMLFormsBaseTestCase):
    def test_admin_sees_read_only_tabs_without_surveyor_action_buttons(self):
        self.client.force_login(self.admin)

        # Inspection Tab
        response = self.client.get(f'/claims/{self.claim.id}/?tab=inspection')
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="photos"')
        self.assertNotContains(response, 'name="documents"')
        self.assertNotContains(response, 'action="/claims/%d/inspection/save/"' % self.claim.id)

        # LOR Tab
        response = self.client.get(f'/claims/{self.claim.id}/?tab=lor')
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'action="/claims/%d/lor/add/"' % self.claim.id)

        # Assessment Tab
        response = self.client.get(f'/claims/{self.claim.id}/?tab=assessment')
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'action="/claims/%d/assessment/save/"' % self.claim.id)
        self.assertNotContains(response, 'action="/claims/%d/assessment/item/add/"' % self.claim.id)

        # FSR Tab
        response = self.client.get(f'/claims/{self.claim.id}/?tab=fsr')
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'action="/claims/%d/report/fsr/save/"' % self.claim.id)
        self.assertNotContains(response, 'action="/claims/%d/report/fsr/submit/"' % self.claim.id)

    def test_surveyor_sees_interactive_controls(self):
        self.client.force_login(self.surveyor)

        # Inspection Tab
        response = self.client.get(f'/claims/{self.claim.id}/?tab=inspection')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="photos"')
        self.assertContains(response, 'name="documents"')

        # LOR Tab
        response = self.client.get(f'/claims/{self.claim.id}/?tab=lor')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Add Requirement')

        # Assessment Tab
        response = self.client.get(f'/claims/{self.claim.id}/?tab=assessment')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Financial Parameters')

        # FSR Tab
        response = self.client.get(f'/claims/{self.claim.id}/?tab=fsr')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Save Draft')
