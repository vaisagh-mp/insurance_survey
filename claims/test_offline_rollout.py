import json
from datetime import date, timedelta
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile

from claims.models import (
    Claim, ClaimStatus, Insurer, Insured, Policy, SurveyAssignment, Priority
)
from documents.models import ClaimDocument, DocumentType, Requirement
from surveys.models import SurveyType, Inspection
from assessments.models import Assessment, AssessmentItem, Invoice
from reports.models import ILA, ISR, FSR, ReportStatus
from accounts.models import SurveyorProfile

User = get_user_model()


class OfflineRolloutTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin_user = User.objects.create_user(
            username='admin_rollout',
            email='admin@rollout.test',
            password='password123',
            role=User.Role.ADMIN,
            is_superuser=True
        )
        self.surveyor_user = User.objects.create_user(
            username='surveyor_rollout',
            email='surveyor@rollout.test',
            password='password123',
            role=User.Role.SURVEYOR
        )
        SurveyorProfile.objects.create(
            user=self.surveyor_user,
            license_number='LIC-ROLLOUT-001',
            license_expiry=date(2028, 1, 1),
            phone='555-0101',
            specialization='Fire & Engineering'
        )

        self.survey_type = SurveyType.objects.get(code='FIRE')
        self.doc_type, _ = DocumentType.objects.get_or_create(code='OTHER', defaults={'name': 'Other Document'})
        self.insurer = Insurer.objects.create(
            company_name='Apex General Insurance',
            branch_name='Downtown',
            address='100 Main St',
            city='Metro City',
            state='State',
            pincode='400001',
            contact_person='John Doe',
            phone='555-0202',
            email='claims@apex.test'
        )
        self.insured = Insured.objects.create(
            name='Alpha Manufacturing Ltd',
            company_name='Alpha Corp',
            address='Plot 5 Industrial Estate',
            city='Metro City',
            state='State',
            pincode='400002',
            phone='555-0303',
            email='info@alpha.test',
            contact_person='Jane Smith'
        )
        now = timezone.now()
        self.policy = Policy.objects.create(
            insurer=self.insurer,
            policy_number='POL-ROLLOUT-001',
            policy_type='Fire Policy',
            start_datetime=now,
            end_datetime=now + timedelta(days=365),
            sum_insured=Decimal('10000000.00'),
            excess=Decimal('25000.00'),
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
            loss_location='Unit 3 Factory',
            claimed_amount=Decimal('50000.00'),
            status=ClaimStatus.ASSIGNED,
            created_by=self.admin_user
        )

        self.assignment = SurveyAssignment.objects.create(
            claim=self.claim,
            surveyor=self.surveyor_user,
            assigned_by=self.admin_user,
            due_date=date(2026, 9, 30),
            status=SurveyAssignment.Status.ASSIGNED
        )

    # ==========================================
    # AREA 1: INSPECTION
    # ==========================================
    def test_area1_inspection_save_html_path(self):
        """Standard form submission should save and redirect."""
        self.client.force_login(self.admin_user)
        data = {
            'inspection_date': '2026-09-10',
            'start_time': '10:00:00',
            'end_time': '12:00:00',
            'location': 'Unit 3 Factory',
            'person_contacted': 'John Doe',
            'contact_number': '555-0101',
            'status': Inspection.Status.SCHEDULED,
            'observations': 'Scheduled inspection for next week',
        }
        resp = self.client.post(f'/claims/{self.claim.id}/inspection/save/', data=data)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(f'/claims/{self.claim.id}/', resp.url)
        self.claim.refresh_from_db()
        self.assertTrue(Inspection.objects.filter(claim=self.claim).exists())

    def test_area1_inspection_save_json_success(self):
        """Dual-accept JSON path should save inspection and return 200/201 JsonResponse."""
        self.client.force_login(self.admin_user)
        payload = {
            'inspection_date': '2026-09-12',
            'start_time': '10:00:00',
            'end_time': '12:00:00',
            'location': 'Unit 3 Factory',
            'person_contacted': 'John Doe',
            'contact_number': '555-0101',
            'status': Inspection.Status.COMPLETED,
            'observations': 'Completed on site via JSON outbox',
            'base_updated_at': self.claim.updated_at.isoformat(),
        }
        resp = self.client.post(
            f'/claims/{self.claim.id}/inspection/save/',
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_ACCEPT='application/json'
        )
        self.assertIn(resp.status_code, [200, 201])
        res_data = resp.json()
        self.assertEqual(res_data['status'], 'success')
        self.assertIn('id', res_data)

    def test_area1_inspection_save_json_validation_failure(self):
        """Invalid JSON inspection data returns 400 JSON with detail and errors."""
        self.client.force_login(self.admin_user)
        payload = {
            'inspection_date': '',  # invalid
            'status': 'INVALID_STATUS',
        }
        resp = self.client.post(
            f'/claims/{self.claim.id}/inspection/save/',
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_ACCEPT='application/json'
        )
        self.assertEqual(resp.status_code, 400)
        res_data = resp.json()
        self.assertIn('detail', res_data)
        self.assertIn('errors', res_data)

    def test_area1_inspection_save_concurrency_conflict(self):
        """Stale base_updated_at should return 409 Conflict."""
        self.client.force_login(self.admin_user)
        stale_ts = (self.claim.updated_at - timedelta(hours=1)).isoformat()
        payload = {
            'inspection_date': '2026-09-15',
            'start_time': '10:00:00',
            'end_time': '12:00:00',
            'location': 'Unit 3 Factory',
            'person_contacted': 'John Doe',
            'contact_number': '555-0101',
            'status': Inspection.Status.SCHEDULED,
            'base_updated_at': stale_ts,
        }
        resp = self.client.post(
            f'/claims/{self.claim.id}/inspection/save/',
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_ACCEPT='application/json'
        )
        self.assertEqual(resp.status_code, 409)
        self.assertIn('detail', resp.json())

    # ==========================================
    # AREA 2: DOCUMENTS
    # ==========================================
    def test_area2_document_verify_json_success(self):
        """Admin verifying document via JSON returns 200 JsonResponse."""
        self.client.force_login(self.admin_user)
        doc = ClaimDocument.objects.create(
            claim=self.claim,
            document_type=self.doc_type,
            file=SimpleUploadedFile('test.pdf', b'%PDF-1.4 test', content_type='application/pdf'),
            description='Site Note',
            uploaded_by=self.surveyor_user
        )
        resp = self.client.post(
            f'/claims/{self.claim.id}/documents/{doc.id}/verify/',
            data=json.dumps({'base_updated_at': doc.uploaded_at.isoformat()}),
            content_type='application/json',
            HTTP_ACCEPT='application/json'
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['status'], 'success')
        doc.refresh_from_db()
        self.assertTrue(doc.verified)

    def test_area2_document_verify_surveyor_forbidden(self):
        """Surveyor attempting to verify document returns 403 JSON."""
        self.client.force_login(self.surveyor_user)
        doc = ClaimDocument.objects.create(
            claim=self.claim,
            document_type=self.doc_type,
            file=SimpleUploadedFile('test2.pdf', b'%PDF-1.4 test', content_type='application/pdf'),
            description='Site Note 2',
            uploaded_by=self.surveyor_user
        )
        resp = self.client.post(
            f'/claims/{self.claim.id}/documents/{doc.id}/verify/',
            data=json.dumps({}),
            content_type='application/json',
            HTTP_ACCEPT='application/json'
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json().get('code'), 'forbidden')

    def test_area2_document_verify_concurrency_conflict(self):
        """Stale base_updated_at on document verify returns 409 JSON."""
        self.client.force_login(self.admin_user)
        doc = ClaimDocument.objects.create(
            claim=self.claim,
            document_type=self.doc_type,
            file=SimpleUploadedFile('test3.pdf', b'%PDF-1.4 test', content_type='application/pdf'),
            description='Site Note 3',
            uploaded_by=self.surveyor_user
        )
        stale_ts = (doc.uploaded_at - timedelta(hours=2)).isoformat()
        resp = self.client.post(
            f'/claims/{self.claim.id}/documents/{doc.id}/verify/',
            data=json.dumps({'base_updated_at': stale_ts}),
            content_type='application/json',
            HTTP_ACCEPT='application/json'
        )
        self.assertEqual(resp.status_code, 409)

    def test_area2_document_upload_concurrency_conflict(self):
        """Stale base_updated_at on document upload returns 409 JSON."""
        self.client.force_login(self.surveyor_user)
        stale_ts = (self.claim.updated_at - timedelta(days=1)).isoformat()
        payload = {
            'document_type': self.doc_type.id,
            'description': 'Stale Document',
            'file_data': 'data:application/pdf;base64,JVBERi0xLjQKJcTl8uXrp...',
            'file_name': 'test.pdf',
            'base_updated_at': stale_ts
        }
        resp = self.client.post(
            f'/claims/{self.claim.id}/documents/upload/',
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_ACCEPT='application/json'
        )
        self.assertEqual(resp.status_code, 409)

    # ==========================================
    # AREA 3: LOR (Loss Optimization Requirements)
    # ==========================================
    def test_area3_lor_add_json_success(self):
        """Add LOR via JSON returns 201 JsonResponse."""
        self.client.force_login(self.admin_user)
        payload = {
            'description': 'Provide fire brigade FIR report',
            'requested_from': Requirement.RequestedFrom.INSURED,
            'requested_date': '2026-09-02',
            'due_date': '2026-09-30',
            'status': Requirement.Status.PENDING
        }
        resp = self.client.post(
            f'/claims/{self.claim.id}/lor/add/',
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_ACCEPT='application/json'
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()['status'], 'success')
        self.assertTrue(Requirement.objects.filter(claim=self.claim, description='Provide fire brigade FIR report').exists())

    def test_area3_lor_add_json_validation_failure(self):
        """Add LOR with missing description returns 400 JSON."""
        self.client.force_login(self.admin_user)
        payload = {'description': ''}
        resp = self.client.post(
            f'/claims/{self.claim.id}/lor/add/',
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_ACCEPT='application/json'
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn('errors', resp.json())

    def test_area3_lor_update_status_surveyor_verified_rejection(self):
        """Rule 2 specific requirement: surveyor attempting to set VERIFIED returns 403 JSON."""
        self.client.force_login(self.surveyor_user)
        lor = Requirement.objects.create(
            claim=self.claim,
            description='Purchase bills',
            requested_date=date(2026, 9, 2),
            status=Requirement.Status.PENDING,
            created_by=self.admin_user
        )
        resp = self.client.post(
            f'/claims/{self.claim.id}/lor/{lor.id}/update-status/',
            data=json.dumps({'status': Requirement.Status.VERIFIED}),
            content_type='application/json',
            HTTP_ACCEPT='application/json'
        )
        self.assertEqual(resp.status_code, 403)
        res_data = resp.json()
        self.assertEqual(res_data.get('code'), 'forbidden')
        self.assertIn('Administrator', res_data.get('detail', ''))

    def test_area3_lor_update_status_admin_verified_success(self):
        """Admin can set VERIFIED returning 200 JSON."""
        self.client.force_login(self.admin_user)
        lor = Requirement.objects.create(
            claim=self.claim,
            description='Repair bills',
            requested_date=date(2026, 9, 2),
            status=Requirement.Status.PENDING,
            created_by=self.admin_user
        )
        resp = self.client.post(
            f'/claims/{self.claim.id}/lor/{lor.id}/update-status/',
            data=json.dumps({'status': Requirement.Status.VERIFIED}),
            content_type='application/json',
            HTTP_ACCEPT='application/json'
        )
        self.assertEqual(resp.status_code, 200)
        lor.refresh_from_db()
        self.assertEqual(lor.status, Requirement.Status.VERIFIED)

    def test_area3_lor_update_status_concurrency_conflict(self):
        """Stale base_updated_at on LOR status update returns 409 JSON."""
        self.client.force_login(self.admin_user)
        lor = Requirement.objects.create(
            claim=self.claim,
            description='Police panchanama',
            requested_date=date(2026, 9, 2),
            status=Requirement.Status.PENDING,
            created_by=self.admin_user
        )
        stale_ts = (lor.updated_at - timedelta(hours=1)).isoformat()
        resp = self.client.post(
            f'/claims/{self.claim.id}/lor/{lor.id}/update-status/',
            data=json.dumps({
                'status': Requirement.Status.RECEIVED,
                'base_updated_at': stale_ts
            }),
            content_type='application/json',
            HTTP_ACCEPT='application/json'
        )
        self.assertEqual(resp.status_code, 409)

    # ==========================================
    # AREA 4: INVOICES (assessments.Invoice)
    # ==========================================
    def test_area4_invoice_add_json_success(self):
        """Add invoice via JSON returns 201 JsonResponse."""
        self.client.force_login(self.admin_user)
        payload = {
            'invoice_number': 'INV-TEST-001',
            'invoice_date': '2026-09-15',
            'vendor_name': 'Metro Machine Works',
            'amount': '45000.00',
            'tax_amount': '0.00'
        }
        resp = self.client.post(
            f'/claims/{self.claim.id}/invoices/add/',
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_ACCEPT='application/json'
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()['status'], 'success')
        self.assertTrue(Invoice.objects.filter(claim=self.claim, invoice_number='INV-TEST-001').exists())

    def test_area4_invoice_verify_json_success_and_conflict(self):
        """Verify invoice returns 200 JSON, and 409 on conflict."""
        self.client.force_login(self.admin_user)
        inv = Invoice.objects.create(
            claim=self.claim,
            invoice_number='INV-TEST-002',
            invoice_date=date(2026, 9, 10),
            vendor_name='Speed Repairs',
            amount=Decimal('12000.00')
        )
        # 1. Conflict case
        stale_ts = (inv.updated_at - timedelta(minutes=30)).isoformat()
        resp_conf = self.client.post(
            f'/claims/{self.claim.id}/invoices/{inv.id}/verify/',
            data=json.dumps({'base_updated_at': stale_ts}),
            content_type='application/json',
            HTTP_ACCEPT='application/json'
        )
        self.assertEqual(resp_conf.status_code, 409)

        # 2. Success case
        resp_ok = self.client.post(
            f'/claims/{self.claim.id}/invoices/{inv.id}/verify/',
            data=json.dumps({'base_updated_at': inv.updated_at.isoformat()}),
            content_type='application/json',
            HTTP_ACCEPT='application/json'
        )
        self.assertEqual(resp_ok.status_code, 200)
        inv.refresh_from_db()
        self.assertTrue(inv.verified)

    def test_area4_invoice_delete_no_json_path(self):
        """Rule 3: claim_invoice_delete has NO JSON path."""
        self.client.force_login(self.admin_user)
        inv = Invoice.objects.create(
            claim=self.claim,
            invoice_number='INV-TEST-DEL',
            invoice_date=date(2026, 9, 10),
            vendor_name='Del Shop',
            amount=Decimal('5000.00')
        )
        resp = self.client.post(
            f'/claims/{self.claim.id}/invoices/{inv.id}/delete/',
            data=json.dumps({}),
            content_type='application/json',
            HTTP_ACCEPT='application/json'
        )
        self.assertEqual(resp.status_code, 302)

    # ==========================================
    # AREA 5: ASSESSMENT
    # ==========================================
    def test_area5_assessment_save_json_success(self):
        """Assessment save via JSON returns 200."""
        self.client.force_login(self.admin_user)
        payload = {
            'salvage_amount': '5000.00',
            'depreciation_amount': '1000.00',
            'underinsurance_percentage': '0.00',
            'policy_excess': '25000.00',
            'other_deductions': '0.00',
            'assessment_remarks': 'Assessed damage in plant',
            'base_updated_at': self.claim.updated_at.isoformat()
        }
        resp = self.client.post(
            f'/claims/{self.claim.id}/assessment/save/',
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_ACCEPT='application/json'
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['status'], 'success')
        self.assertTrue(Assessment.objects.filter(claim=self.claim).exists())

    def test_area5_assessment_save_concurrency_conflict(self):
        """Assessment save with stale base_updated_at returns 409."""
        self.client.force_login(self.admin_user)
        stale_ts = (self.claim.updated_at - timedelta(hours=3)).isoformat()
        payload = {
            'salvage_amount': '2000.00',
            'base_updated_at': stale_ts
        }
        resp = self.client.post(
            f'/claims/{self.claim.id}/assessment/save/',
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_ACCEPT='application/json'
        )
        self.assertEqual(resp.status_code, 409)

    def test_area5_assessment_item_add_and_edit_json(self):
        """Assessment item add and edit via JSON path."""
        self.client.force_login(self.admin_user)
        assessment = Assessment.objects.create(
            claim=self.claim,
            created_by=self.admin_user
        )
        # 1. Add item
        add_payload = {
            'description': 'Conveyor Belt replacement',
            'quantity': '1.00',
            'rate': '12000.00',
            'claimed_amount': '15000.00'
        }
        resp_add = self.client.post(
            f'/claims/{self.claim.id}/assessment/item/add/',
            data=json.dumps(add_payload),
            content_type='application/json',
            HTTP_ACCEPT='application/json'
        )
        self.assertEqual(resp_add.status_code, 201)
        item_id = resp_add.json()['id']

        item = AssessmentItem.objects.get(id=item_id)
        self.assertEqual(item.description, 'Conveyor Belt replacement')

        # 2. Edit item conflict
        stale_ts = (assessment.updated_at - timedelta(minutes=15)).isoformat()
        resp_edit_conf = self.client.post(
            f'/claims/{self.claim.id}/assessment/item/{item.id}/edit/',
            data=json.dumps({
                'description': 'Conveyor Belt v2',
                'quantity': '1.00',
                'rate': '11000.00',
                'claimed_amount': '15000.00',
                'base_updated_at': stale_ts
            }),
            content_type='application/json',
            HTTP_ACCEPT='application/json'
        )
        self.assertEqual(resp_edit_conf.status_code, 409)

        # 3. Edit item success
        resp_edit_ok = self.client.post(
            f'/claims/{self.claim.id}/assessment/item/{item.id}/edit/',
            data=json.dumps({
                'description': 'Conveyor Belt updated',
                'quantity': '1.00',
                'rate': '11500.00',
                'claimed_amount': '15000.00',
                'base_updated_at': assessment.updated_at.isoformat()
            }),
            content_type='application/json',
            HTTP_ACCEPT='application/json'
        )
        self.assertEqual(resp_edit_ok.status_code, 200)
        item.refresh_from_db()
        self.assertEqual(item.description, 'Conveyor Belt updated')

    def test_area5_assessment_item_delete_no_json_path(self):
        """Rule 3: claim_assessment_item_delete has NO JSON path."""
        self.client.force_login(self.admin_user)
        assessment = Assessment.objects.create(claim=self.claim, created_by=self.admin_user)
        item = AssessmentItem.objects.create(
            assessment=assessment,
            description='To Delete',
            quantity=Decimal('1.00'),
            rate=Decimal('1000.00'),
            claimed_amount=Decimal('1000.00')
        )
        resp = self.client.post(
            f'/claims/{self.claim.id}/assessment/item/{item.id}/delete/',
            data=json.dumps({}),
            content_type='application/json',
            HTTP_ACCEPT='application/json'
        )
        self.assertEqual(resp.status_code, 302)

    # ==========================================
    # AREA 6: REPORTS
    # ==========================================
    def test_area6_report_save_ila_dual_accept_and_concurrency(self):
        """Dedicated test for ILA's JSON dual-accept path on claim_report_save (Rule 1 & Rule 5)."""
        self.client.force_login(self.admin_user)
        ila_payload = {
            'visit_date': '2026-09-02',
            'visit_start_time': '10:00:00',
            'visit_end_time': '12:00:00',
            'person_contacted': 'Manager Roy',
            'contact_number': '555-1234',
            'survey_and_inspection': 'Inspected damaged area',
            'extent_of_damage': 'Damage to conveyor',
            'cause_of_damage': 'Short circuit in wiring',
            'salvage_prospect': 'Minimal salvage value',
            'estimated_loss': '45000.00',
            'policy_liability': 'Covered under fire policy',
            'budgetary_reserve': '50000.00',
            'base_updated_at': self.claim.updated_at.isoformat()
        }

        # 1. HTML form path redirects
        resp_html = self.client.post(
            f'/claims/{self.claim.id}/report/ila/save/',
            data=ila_payload
        )
        self.assertEqual(resp_html.status_code, 302)
        self.assertIn(f'/claims/{self.claim.id}/?tab=ila', resp_html['Location'])
        self.assertTrue(ILA.objects.filter(claim=self.claim).exists())
        existing_ila = ILA.objects.filter(claim=self.claim).first()

        # 2. JSON update path returns 200/201 with JSON body
        ila_payload['extent_of_damage'] = 'Damage to conveyor updated via JSON'
        ila_payload['base_updated_at'] = existing_ila.updated_at.isoformat()
        resp_json = self.client.post(
            f'/claims/{self.claim.id}/report/ila/save/',
            data=json.dumps(ila_payload),
            content_type='application/json',
            HTTP_ACCEPT='application/json'
        )
        self.assertEqual(resp_json.status_code, 200)
        self.assertEqual(resp_json.json()['status'], 'success')
        self.assertEqual(resp_json.json()['report_type'], 'ILA')
        existing_ila.refresh_from_db()
        self.assertEqual(existing_ila.extent_of_damage, 'Damage to conveyor updated via JSON')

        # 3. Optimistic concurrency conflict on ILA (Rule 5)
        stale_ts = (existing_ila.updated_at - timedelta(hours=2)).isoformat()
        ila_payload['base_updated_at'] = stale_ts
        resp_conf = self.client.post(
            f'/claims/{self.claim.id}/report/ila/save/',
            data=json.dumps(ila_payload),
            content_type='application/json',
            HTTP_ACCEPT='application/json'
        )
        self.assertEqual(resp_conf.status_code, 409)

        # 4. JSON validation failure returns 400 with errors dict
        bad_payload = {'visit_date': 'invalid-date'}
        resp_bad = self.client.post(
            f'/claims/{self.claim.id}/report/ila/save/',
            data=json.dumps(bad_payload),
            content_type='application/json',
            HTTP_ACCEPT='application/json'
        )
        self.assertEqual(resp_bad.status_code, 400)
        self.assertIn('errors', resp_bad.json())

    def test_area6_report_save_isr_skip_justification(self):
        """ISR report skip_justification validation (separate from FSR)."""
        self.client.force_login(self.admin_user)
        base_isr_payload = {
            'report_date': '2026-09-10',
            'introduction': 'Intro text',
            'occurrence_details': 'Occurrence details text',
            'survey_details': 'Survey conducted on site',
            'extent_of_damage': 'Damage to line',
            'cause_of_loss': 'Electrical short circuit',
            'initial_assessment': 'Loss estimated around 40k',
            'policy_liability': 'Liability admitted',
        }
        # When skipping without justification: returns 400
        payload_invalid = {**base_isr_payload, 'skip_justification': ''}
        resp_invalid = self.client.post(
            f'/claims/{self.claim.id}/report/isr/save/',
            data=json.dumps(payload_invalid),
            content_type='application/json',
            HTTP_ACCEPT='application/json'
        )
        self.assertEqual(resp_invalid.status_code, 400)
        self.assertIn('skip_justification', resp_invalid.json().get('errors', {}))

        # With justification: succeeds
        payload_valid = {**base_isr_payload, 'skip_justification': 'Small claim under threshold'}
        resp_valid = self.client.post(
            f'/claims/{self.claim.id}/report/isr/save/',
            data=json.dumps(payload_valid),
            content_type='application/json',
            HTTP_ACCEPT='application/json'
        )
        self.assertIn(resp_valid.status_code, [200, 201])
        self.assertTrue(ISR.objects.filter(claim=self.claim).exists())

    def test_area6_report_save_fsr_skip_justification(self):
        """Dedicated test for FSR's own skip_justification requirement, separate from ISR."""
        self.client.force_login(self.admin_user)
        base_fsr_payload = {
            'report_date': '2026-09-12',
            'introduction': 'Final survey introduction',
            'occurrence_details': 'Fire outbreak in manufacturing unit',
            'survey_details': 'Detailed survey conducted on site',
            'extent_of_loss': 'Complete damage to electrical motor',
            'cause_of_loss': 'Electrical short circuit and overheating',
            'value_at_risk': '500000.00',
            'sum_insured': '500000.00',
            'underinsurance_percentage': '0.00',
            'salvage_description': 'Burnt copper scrap',
            'salvage_amount': '5000.00',
            'insured_claim_description': 'Replacement of motor assembly',
            'admissibility': 'Loss is admissible under Section 1',
            'final_opinion': 'Recommend settlement subject to excess',
            'remarks': 'All verified'
        }

        # 1. When claim has not completed LOR/Assessment and skip_justification is empty: returns 400
        payload_invalid = {**base_fsr_payload, 'skip_justification': ''}
        resp_invalid = self.client.post(
            f'/claims/{self.claim.id}/report/fsr/save/',
            data=json.dumps(payload_invalid),
            content_type='application/json',
            HTTP_ACCEPT='application/json'
        )
        self.assertEqual(resp_invalid.status_code, 400)
        self.assertIn('skip_justification', resp_invalid.json().get('errors', {}))
        self.assertEqual(resp_invalid.json()['detail'], 'Reason for skipping LOR/Assessment is required.')

        # 2. With valid skip_justification: returns 200/201 and creates FSR
        payload_valid = {**base_fsr_payload, 'skip_justification': 'Fast-track assessment approved by regional manager'}
        resp_valid = self.client.post(
            f'/claims/{self.claim.id}/report/fsr/save/',
            data=json.dumps(payload_valid),
            content_type='application/json',
            HTTP_ACCEPT='application/json'
        )
        self.assertIn(resp_valid.status_code, [200, 201])
        self.assertEqual(resp_valid.json()['status'], 'success')
        self.assertEqual(resp_valid.json()['report_type'], 'FSR')
        self.assertTrue(FSR.objects.filter(claim=self.claim).exists())

    # ==========================================
    # AREA 8: CLAIM MANAGEMENT & MASTER DATA
    # ==========================================
    def test_area8_claim_create_json_success_and_validation(self):
        """Dual-accept claim_create."""
        self.client.force_login(self.admin_user)
        payload = {
            'claim_number': 'CLM-TEST-JSON-001',
            'survey_type': self.survey_type.id,
            'insurer': self.insurer.id,
            'insured': self.insured.id,
            'policy': self.policy.id,
            'instruction_date': '2026-09-05',
            'instruction_source': 'Portal',
            'date_of_loss': '2026-09-02',
            'nature_of_loss': 'Machine failure',
            'loss_location': 'Warehouse 4',
            'claimed_amount': '75000.00',
            'priority': Priority.HIGH
        }
        resp = self.client.post(
            '/claims/create/',
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_ACCEPT='application/json'
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()['status'], 'success')
        new_claim = Claim.objects.get(claim_number='CLM-TEST-JSON-001')
        self.assertEqual(new_claim.claimed_amount, Decimal('75000.00'))

        resp_bad = self.client.post(
            '/claims/create/',
            data=json.dumps({'instruction_source': ''}),
            content_type='application/json',
            HTTP_ACCEPT='application/json'
        )
        self.assertEqual(resp_bad.status_code, 400)
        self.assertIn('errors', resp_bad.json())

    def test_area8_claim_assign_surveyor_routes(self):
        """Direct web-route tests for claim_assign_surveyor (both HTML and JSON)."""
        self.client.force_login(self.admin_user)
        new_surveyor = User.objects.create_user(
            username='surveyor_2', email='s2@test.test', password='password', role=User.Role.SURVEYOR
        )
        # HTML form post
        resp_html = self.client.post(
            f'/claims/{self.claim.id}/assign/',
            data={'surveyor': new_surveyor.id, 'notes': 'HTML assignment'}
        )
        self.assertEqual(resp_html.status_code, 302)

        # JSON post
        resp_json = self.client.post(
            f'/claims/{self.claim.id}/assign/',
            data=json.dumps({'surveyor': self.surveyor_user.id, 'notes': 'JSON reassignment'}),
            content_type='application/json',
            HTTP_ACCEPT='application/json'
        )
        self.assertEqual(resp_json.status_code, 200)
        self.assertEqual(resp_json.json()['status'], 'success')

        # Non-admin non-superuser forbidden
        self.client.force_login(self.surveyor_user)
        resp_forbid = self.client.post(
            f'/claims/{self.claim.id}/assign/',
            data=json.dumps({'surveyor': self.surveyor_user.id}),
            content_type='application/json',
            HTTP_ACCEPT='application/json'
        )
        self.assertEqual(resp_forbid.status_code, 403)

    def test_area8_claim_approve_and_close(self):
        """Approve and close claim via JSON."""
        self.client.force_login(self.admin_user)
        self.claim.status = ClaimStatus.REPORT_SUBMITTED
        self.claim.save()

        # Create a submitted report so claim can be approved and closed
        now = timezone.now()
        ILA.objects.create(
            claim=self.claim,
            report_number='REP-ILA-CLOSE-001',
            report_date=date(2026, 9, 5),
            instruction_date=date(2026, 9, 1),
            instruction_source='Email',
            surveyor=self.surveyor_user,
            prepared_by=self.surveyor_user,
            visit_date=date(2026, 9, 2),
            visit_start_time='10:00:00',
            visit_end_time='12:00:00',
            inspection_location='Unit 3 Factory',
            person_contacted='Roy',
            contact_number='555-1234',
            policy_number='POL-001',
            policy_type='Fire Policy',
            commodity='Plant',
            sum_insured=Decimal('10000000.00'),
            policy_excess=Decimal('25000.00'),
            survey_and_inspection='Inspected',
            extent_of_damage='Damaged',
            cause_of_damage='Fire',
            salvage_prospect='None',
            estimated_loss=Decimal('50000.00'),
            claimed_amount=Decimal('50000.00'),
            policy_liability='Admitted',
            budgetary_reserve=Decimal('50000.00'),
            status=ReportStatus.SUBMITTED,
            submitted_at=now
        )

        resp = self.client.post(
            f'/claims/{self.claim.id}/approve-and-close/',
            data=json.dumps({'remarks': 'All verified and settled'}),
            content_type='application/json',
            HTTP_ACCEPT='application/json'
        )
        self.assertEqual(resp.status_code, 200)
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, ClaimStatus.CLOSED)

    def test_area8_master_data_popout_success_and_direct_navigation_fallback(self):
        """Rule 6 popout_success template behavior and fallback when navigating directly."""
        self.client.force_login(self.admin_user)

        # 1. Popout navigation: returns popout_success.html with redirect_url and BroadcastChannel
        resp_ins_pop = self.client.post(
            '/insurers/add/?popout=1&opened_as_popout=1',
            data={
                'company_name': 'Popout Insurer Ltd',
                'branch_name': 'Central',
                'address': '200 High St',
                'city': 'City',
                'state': 'State',
                'pincode': '110001',
                'contact_person': 'Bob',
                'phone': '555-9999',
                'email': 'popout@insurer.test',
                'is_active': True
            }
        )
        self.assertEqual(resp_ins_pop.status_code, 200)
        self.assertContains(resp_ins_pop, 'soteria_master_data')
        self.assertContains(resp_ins_pop, '/insurers/')
        self.assertContains(resp_ins_pop, 'Return to List')

        resp_ind_pop = self.client.post(
            '/insured/add/?popout=1',
            data={
                'name': 'Popout Insured Ltd',
                'company_name': 'Popout Insured Corp',
                'address': '201 High St',
                'city': 'City',
                'state': 'State',
                'pincode': '110002',
                'contact_person': 'Alice',
                'phone': '555-8888',
                'email': 'popout@insured.test'
            }
        )
        self.assertEqual(resp_ind_pop.status_code, 200)
        self.assertContains(resp_ind_pop, '/insured/')

        now = timezone.now()
        resp_pol_pop = self.client.post(
            '/policies/add/?popout=1',
            data={
                'insurer': self.insurer.id,
                'policy_number': 'POL-POPOUT-001',
                'policy_type': 'Fire Policy',
                'start_datetime': now.strftime('%Y-%m-%dT%H:%M'),
                'end_datetime': (now + timedelta(days=365)).strftime('%Y-%m-%dT%H:%M'),
                'sum_insured': '5000000.00',
                'excess': '10000.00',
                'commodity': 'Machinery',
                'subject_matter': 'Plant'
            }
        )
        self.assertEqual(resp_pol_pop.status_code, 200)
        self.assertContains(resp_pol_pop, '/policies/')

        # 2. Direct navigation fallback: normal redirect-to-list behavior (no popout_success rendered)
        resp_ins_direct = self.client.post(
            '/insurers/add/',
            data={
                'company_name': 'Direct Insurer Ltd',
                'branch_name': 'East',
                'address': '300 East St',
                'city': 'City',
                'state': 'State',
                'pincode': '110003',
                'contact_person': 'Charlie',
                'phone': '555-7777',
                'email': 'direct@insurer.test',
                'is_active': True
            }
        )
        self.assertEqual(resp_ins_direct.status_code, 302)
        self.assertEqual(resp_ins_direct['Location'], '/insurers/')

        resp_ind_direct = self.client.post(
            '/insured/add/',
            data={
                'name': 'Direct Insured Ltd',
                'company_name': 'Direct Insured Corp',
                'address': '301 East St',
                'city': 'City',
                'state': 'State',
                'pincode': '110004',
                'contact_person': 'David',
                'phone': '555-6666',
                'email': 'direct@insured.test'
            }
        )
        self.assertEqual(resp_ind_direct.status_code, 302)
        self.assertEqual(resp_ind_direct['Location'], '/insured/')

        resp_pol_direct = self.client.post(
            '/policies/add/',
            data={
                'insurer': self.insurer.id,
                'policy_number': 'POL-DIRECT-001',
                'policy_type': 'Fire Policy',
                'start_datetime': now.strftime('%Y-%m-%dT%H:%M'),
                'end_datetime': (now + timedelta(days=365)).strftime('%Y-%m-%dT%H:%M'),
                'sum_insured': '5000000.00',
                'excess': '10000.00',
                'commodity': 'Machinery',
                'subject_matter': 'Plant'
            }
        )
        self.assertEqual(resp_pol_direct.status_code, 302)
        self.assertEqual(resp_pol_direct['Location'], '/policies/')

    def test_area8_insurer_edit_dual_accept_and_concurrency(self):
        """Direct, dedicated test for insurer_edit dual-accept and concurrency."""
        self.client.force_login(self.admin_user)
        ins = Insurer.objects.create(
            company_name='Edit Insurer Direct Ltd',
            branch_name='South',
            address='123 South St',
            city='City',
            state='State',
            pincode='110005',
            contact_person='Eve',
            phone='555-5555',
            email='edit@insurer.test',
            is_active=True
        )

        # 1. HTML form path
        resp_html = self.client.post(
            f'/insurers/{ins.id}/edit/',
            data={
                'company_name': 'Edit Insurer HTML',
                'branch_name': 'South',
                'address': '123 South St',
                'city': 'City',
                'state': 'State',
                'pincode': '110005',
                'contact_person': 'Eve',
                'phone': '555-5555',
                'email': 'edit@insurer.test',
                'is_active': True
            }
        )
        self.assertEqual(resp_html.status_code, 302)
        self.assertEqual(resp_html['Location'], '/insurers/')
        ins.refresh_from_db()
        self.assertEqual(ins.company_name, 'Edit Insurer HTML')

        # 2. JSON edit path
        resp_json = self.client.post(
            f'/insurers/{ins.id}/edit/',
            data=json.dumps({
                'company_name': 'Edit Insurer JSON',
                'branch_name': 'South',
                'address': '123 South St',
                'city': 'City',
                'state': 'State',
                'pincode': '110005',
                'contact_person': 'Eve',
                'phone': '555-5555',
                'email': 'edit@insurer.test',
                'is_active': True,
                'base_updated_at': ins.updated_at.isoformat()
            }),
            content_type='application/json',
            HTTP_ACCEPT='application/json'
        )
        self.assertEqual(resp_json.status_code, 200)
        self.assertEqual(resp_json.json()['status'], 'success')
        ins.refresh_from_db()
        self.assertEqual(ins.company_name, 'Edit Insurer JSON')

        # 3. Concurrency conflict
        stale_ts = (ins.updated_at - timedelta(hours=1)).isoformat()
        resp_conf = self.client.post(
            f'/insurers/{ins.id}/edit/',
            data=json.dumps({
                'company_name': 'Edit Insurer Conflict',
                'branch_name': 'South',
                'address': '123 South St',
                'city': 'City',
                'state': 'State',
                'pincode': '110005',
                'contact_person': 'Eve',
                'phone': '555-5555',
                'email': 'edit@insurer.test',
                'is_active': True,
                'base_updated_at': stale_ts
            }),
            content_type='application/json',
            HTTP_ACCEPT='application/json'
        )
        self.assertEqual(resp_conf.status_code, 409)

        # 4. Validation error
        resp_bad = self.client.post(
            f'/insurers/{ins.id}/edit/',
            data=json.dumps({'company_name': ''}),
            content_type='application/json',
            HTTP_ACCEPT='application/json'
        )
        self.assertEqual(resp_bad.status_code, 400)
        self.assertIn('errors', resp_bad.json())

    def test_area8_insured_edit_dual_accept_and_concurrency(self):
        """Direct, dedicated test for insured_edit dual-accept and concurrency."""
        self.client.force_login(self.admin_user)
        ind = Insured.objects.create(
            name='Alpha Insured Direct',
            company_name='Alpha Corp',
            address='Plot 5 Industrial Estate',
            city='Metro City',
            state='State',
            pincode='400002',
            phone='555-0303',
            email='info@alpha.test',
            contact_person='Jane Smith'
        )

        # 1. HTML form path
        resp_html = self.client.post(
            f'/insured/{ind.id}/edit/',
            data={
                'name': 'Alpha Insured HTML',
                'company_name': 'Alpha Corp',
                'address': 'Plot 5 Industrial Estate',
                'city': 'Metro City',
                'state': 'State',
                'pincode': '400002',
                'phone': '555-0303',
                'email': 'info@alpha.test',
                'contact_person': 'Jane Smith'
            }
        )
        self.assertEqual(resp_html.status_code, 302)
        self.assertEqual(resp_html['Location'], '/insured/')
        ind.refresh_from_db()
        self.assertEqual(ind.name, 'Alpha Insured HTML')

        # 2. JSON edit path
        resp_json = self.client.post(
            f'/insured/{ind.id}/edit/',
            data=json.dumps({
                'name': 'Alpha Insured JSON',
                'company_name': 'Alpha Corp',
                'address': 'Plot 5 Industrial Estate',
                'city': 'Metro City',
                'state': 'State',
                'pincode': '400002',
                'phone': '555-0303',
                'email': 'info@alpha.test',
                'contact_person': 'Jane Smith',
                'base_updated_at': ind.updated_at.isoformat()
            }),
            content_type='application/json',
            HTTP_ACCEPT='application/json'
        )
        self.assertEqual(resp_json.status_code, 200)
        self.assertEqual(resp_json.json()['status'], 'success')
        ind.refresh_from_db()
        self.assertEqual(ind.name, 'Alpha Insured JSON')

        # 3. Concurrency conflict
        stale_ts = (ind.updated_at - timedelta(hours=1)).isoformat()
        resp_conf = self.client.post(
            f'/insured/{ind.id}/edit/',
            data=json.dumps({
                'name': 'Alpha Insured Conflict',
                'company_name': 'Alpha Corp',
                'address': 'Plot 5 Industrial Estate',
                'city': 'Metro City',
                'state': 'State',
                'pincode': '400002',
                'phone': '555-0303',
                'email': 'info@alpha.test',
                'contact_person': 'Jane Smith',
                'base_updated_at': stale_ts
            }),
            content_type='application/json',
            HTTP_ACCEPT='application/json'
        )
        self.assertEqual(resp_conf.status_code, 409)

        # 4. Validation error
        resp_bad = self.client.post(
            f'/insured/{ind.id}/edit/',
            data=json.dumps({'name': ''}),
            content_type='application/json',
            HTTP_ACCEPT='application/json'
        )
        self.assertEqual(resp_bad.status_code, 400)
        self.assertIn('errors', resp_bad.json())

    def test_area8_policy_edit_dual_accept_and_concurrency(self):
        """Direct, dedicated test for policy_edit dual-accept and concurrency."""
        self.client.force_login(self.admin_user)
        pol = self.policy

        # 1. HTML form path
        resp_html = self.client.post(
            f'/policies/{pol.id}/edit/',
            data={
                'insurer': self.insurer.id,
                'policy_number': 'POL-ROLLOUT-001-HTML',
                'policy_type': 'Fire Policy',
                'start_datetime': pol.start_datetime.strftime('%Y-%m-%dT%H:%M'),
                'end_datetime': pol.end_datetime.strftime('%Y-%m-%dT%H:%M'),
                'sum_insured': '11000000.00',
                'excess': '25000.00',
                'commodity': 'Plant & Machinery',
                'subject_matter': 'Factory Building'
            }
        )
        self.assertEqual(resp_html.status_code, 302)
        self.assertEqual(resp_html['Location'], '/policies/')
        pol.refresh_from_db()
        self.assertEqual(pol.policy_number, 'POL-ROLLOUT-001-HTML')

        # 2. JSON edit path
        resp_json = self.client.post(
            f'/policies/{pol.id}/edit/',
            data=json.dumps({
                'insurer': self.insurer.id,
                'policy_number': 'POL-ROLLOUT-001-JSON',
                'policy_type': 'Fire Policy',
                'start_datetime': pol.start_datetime.strftime('%Y-%m-%dT%H:%M'),
                'end_datetime': pol.end_datetime.strftime('%Y-%m-%dT%H:%M'),
                'sum_insured': '12000000.00',
                'excess': '30000.00',
                'commodity': 'Plant & Machinery',
                'subject_matter': 'Factory Building',
                'base_updated_at': pol.updated_at.isoformat()
            }),
            content_type='application/json',
            HTTP_ACCEPT='application/json'
        )
        self.assertEqual(resp_json.status_code, 200)
        self.assertEqual(resp_json.json()['status'], 'success')
        pol.refresh_from_db()
        self.assertEqual(pol.policy_number, 'POL-ROLLOUT-001-JSON')

        # 3. Concurrency conflict
        stale_ts = (pol.updated_at - timedelta(hours=1)).isoformat()
        resp_conf = self.client.post(
            f'/policies/{pol.id}/edit/',
            data=json.dumps({
                'insurer': self.insurer.id,
                'policy_number': 'POL-ROLLOUT-001-CONF',
                'policy_type': 'Fire Policy',
                'start_datetime': pol.start_datetime.strftime('%Y-%m-%dT%H:%M'),
                'end_datetime': pol.end_datetime.strftime('%Y-%m-%dT%H:%M'),
                'sum_insured': '12000000.00',
                'excess': '30000.00',
                'commodity': 'Plant & Machinery',
                'subject_matter': 'Factory Building',
                'base_updated_at': stale_ts
            }),
            content_type='application/json',
            HTTP_ACCEPT='application/json'
        )
        self.assertEqual(resp_conf.status_code, 409)

        # 4. Validation error
        resp_bad = self.client.post(
            f'/policies/{pol.id}/edit/',
            data=json.dumps({'policy_number': ''}),
            content_type='application/json',
            HTTP_ACCEPT='application/json'
        )
        self.assertEqual(resp_bad.status_code, 400)
        self.assertIn('errors', resp_bad.json())

    def test_area8_rule6_dependency_replay_flow(self):
        """Rule 6 dependency ordered simulation:
        Client creates Insurer offline with tempId, then creates Claim referencing tempId.
        Verify outbox replay flow substitutes real ID and completes claim creation.
        """
        self.client.force_login(self.admin_user)
        temp_insurer_id = 'temp_insurer_999'

        # Step 1: Insurer replay
        insurer_payload = {
            'company_name': 'Sync Replay Insurer',
            'branch_name': 'North',
            'address': '55 North Road',
            'city': 'Metro City',
            'state': 'State',
            'pincode': '400005',
            'contact_person': 'Sync Lead',
            'phone': '555-7788',
            'email': 'replay@insurer.test',
            'is_active': True
        }
        resp_ins = self.client.post(
            '/insurers/add/',
            data=json.dumps(insurer_payload),
            content_type='application/json',
            HTTP_ACCEPT='application/json'
        )
        self.assertEqual(resp_ins.status_code, 201)
        ins_data = resp_ins.json()
        real_insurer_id = ins_data['id']
        self.assertIsInstance(real_insurer_id, int)

        real_insurer = Insurer.objects.get(id=real_insurer_id)
        now = timezone.now()
        replay_policy = Policy.objects.create(
            insurer=real_insurer,
            policy_number='POL-REPLAY-999',
            policy_type='Fire Policy',
            start_datetime=now,
            end_datetime=now + timedelta(days=365),
            sum_insured=Decimal('5000000.00'),
            excess=Decimal('10000.00'),
            commodity='General',
            subject_matter='Building'
        )

        # Step 2: Simulating JS outbox substitution of temp_insurer_id -> real_insurer_id
        claim_payload = {
            'claim_number': 'CLM-DEP-REPLAY-001',
            'survey_type': self.survey_type.id,
            'insurer': temp_insurer_id,  # Initially holding temp ID
            'insured': self.insured.id,
            'policy': replay_policy.id,
            'instruction_date': '2026-09-08',
            'instruction_source': 'Agent',
            'date_of_loss': '2026-09-06',
            'nature_of_loss': 'Water damage',
            'loss_location': 'Basement',
            'claimed_amount': '30000.00',
            'priority': Priority.MEDIUM
        }

        # Verify that sending claim with unresolved temp ID fails validation:
        resp_bad = self.client.post(
            '/claims/create/',
            data=json.dumps(claim_payload),
            content_type='application/json',
            HTTP_ACCEPT='application/json'
        )
        self.assertEqual(resp_bad.status_code, 400)

        # Perform the client-side outbox substitution:
        claim_payload['insurer'] = real_insurer_id
        resp_good = self.client.post(
            '/claims/create/',
            data=json.dumps(claim_payload),
            content_type='application/json',
            HTTP_ACCEPT='application/json'
        )
        if resp_good.status_code != 201:
            print("RESP_GOOD ERRORS:", resp_good.json())
        self.assertEqual(resp_good.status_code, 201)
        created_claim = Claim.objects.get(claim_number='CLM-DEP-REPLAY-001')
        self.assertEqual(created_claim.insurer.id, real_insurer_id)
