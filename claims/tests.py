from datetime import date, datetime
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from django.utils import timezone
from surveys.models import SurveyType
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
from claims.services import transition_claim_status
from reports.models import AuditLog

User = get_user_model()


class ClaimsModelTests(TestCase):
    def setUp(self):
        # Create users
        self.admin_user = User.objects.create_user(
            username='claim_admin',
            email='admin@claim.test',
            password='password123',
            role=User.Role.ADMIN
        )
        self.surveyor_user = User.objects.create_user(
            username='claim_surveyor',
            email='surveyor@claim.test',
            password='password123',
            role=User.Role.SURVEYOR
        )
        self.surveyor_user2 = User.objects.create_user(
            username='claim_surveyor_2',
            email='surveyor2@claim.test',
            password='password123',
            role=User.Role.SURVEYOR
        )

        # Get survey type
        self.survey_type = SurveyType.objects.get(code='MARINE')

        # Create Insurer
        self.insurer = Insurer.objects.create(
            company_name='National General Insurance Co',
            branch_name='Downtown Corporate Branch',
            address='Suite 400, Financial Plaza',
            city='Metropolis',
            state='State',
            pincode='400001',
            contact_person='Jane Smith',
            phone='+1-555-0101',
            email='claims@nationalgen.com'
        )

        # Create Insured
        self.insured = Insured.objects.create(
            name='Pacific Cargo Logistics Ltd',
            company_name='Pacific Cargo Corp',
            address='Pier 12, Harbor Road',
            city='Port City',
            state='State',
            pincode='400002',
            phone='+1-555-0102',
            email='logistics@pacificcargo.com',
            gstin='27AAAAA0000A1Z5',
            contact_person='Robert Green'
        )

        # Create Policy
        now = timezone.now()
        self.policy = Policy.objects.create(
            insurer=self.insurer,
            policy_number='POL-MAR-2026-9901',
            policy_type='Marine Cargo Open Policy',
            start_datetime=now,
            end_datetime=now + timezone.timedelta(days=365),
            sum_insured=Decimal('5000000.00'),
            excess=Decimal('25000.00'),
            commodity='Electronics & Semiconductor Parts',
            subject_matter='Consignment in transit from Factory to Seaport',
            remarks='Standard all-risk marine clause'
        )

    def _create_sample_claim(self):
        return Claim.objects.create(
            survey_type=self.survey_type,
            insurer=self.insurer,
            insured=self.insured,
            policy=self.policy,
            instruction_date=date(2026, 9, 10),
            instruction_source='Email notification from underwriter',
            date_of_loss=date(2026, 9, 8),
            nature_of_loss='Water ingress damage during heavy rainfall',
            loss_location='Port Terminal Container Yard Bay 4',
            claimed_amount=Decimal('450000.00'),
            priority=Priority.HIGH,
            status=ClaimStatus.NEW,
            created_by=self.admin_user
        )

    def test_insurer_and_insured_creation(self):
        self.assertEqual(str(self.insurer), 'National General Insurance Co - Downtown Corporate Branch')
        self.assertEqual(str(self.insured), 'Pacific Cargo Logistics Ltd (Pacific Cargo Corp)')
        self.assertTrue(self.insurer.is_active)
        self.assertTrue(self.insured.is_active)

    def test_policy_decimal_fields(self):
        self.assertIsInstance(self.policy.sum_insured, Decimal)
        self.assertIsInstance(self.policy.excess, Decimal)
        self.assertEqual(self.policy.sum_insured, Decimal('5000000.00'))
        self.assertEqual(self.policy.excess, Decimal('25000.00'))

    def test_claim_auto_generated_number(self):
        claim1 = self._create_sample_claim()
        self.assertTrue(claim1.claim_number.startswith('CLM-'))
        self.assertEqual(claim1.claim_number, 'CLM-00001')

        claim2 = Claim.objects.create(
            survey_type=self.survey_type,
            insurer=self.insurer,
            insured=self.insured,
            policy=self.policy,
            instruction_date=date(2026, 9, 11),
            instruction_source='Portal claim intimation',
            date_of_loss=date(2026, 9, 9),
            nature_of_loss='Transit collision impact',
            loss_location='National Highway 48 km marker 122',
            claimed_amount=Decimal('120000.00'),
            priority=Priority.MEDIUM,
            status=ClaimStatus.NEW,
            created_by=self.admin_user
        )
        self.assertEqual(claim2.claim_number, 'CLM-00002')

    def test_claim_creation_audit_logged(self):
        claim = self._create_sample_claim()
        audit = AuditLog.objects.filter(
            action='CLAIM_CREATED',
            model_name='Claim',
            object_id=str(claim.pk)
        ).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.user, self.admin_user)
        self.assertIn(claim.claim_number, audit.description)

    def test_survey_assignment_audit_logged(self):
        claim = self._create_sample_claim()

        assignment = SurveyAssignment.objects.create(
            claim=claim,
            surveyor=self.surveyor_user,
            assigned_by=self.admin_user,
            due_date=date(2026, 9, 20),
            priority=Priority.HIGH,
            instructions='Inspect cargo packaging',
            status=SurveyAssignment.Status.ASSIGNED
        )

        audit_create = AuditLog.objects.filter(
            action='SURVEYOR_ASSIGNED',
            object_id=str(claim.pk)
        ).first()
        self.assertIsNotNone(audit_create)
        self.assertIn(self.surveyor_user.username, audit_create.description)

        # Reassign to surveyor2
        assignment.surveyor = self.surveyor_user2
        assignment.save()

        audit_update = AuditLog.objects.filter(
            action='SURVEYOR_REASSIGNED',
            object_id=str(claim.pk)
        ).first()
        self.assertIsNotNone(audit_update)
        self.assertIn(self.surveyor_user2.username, audit_update.description)

    def test_claim_indexes_present(self):
        index_fields = [idx.fields for idx in Claim._meta.indexes]
        self.assertIn(['status'], index_fields)
        self.assertIn(['survey_type'], index_fields)

    def test_transition_claim_status_success(self):
        claim = self._create_sample_claim()
        self.assertEqual(claim.status, ClaimStatus.NEW)

        # Transition NEW -> ASSIGNED
        factory = RequestFactory()
        request = factory.post('/', REMOTE_ADDR='192.168.1.50')
        transition_claim_status(
            claim=claim,
            new_status=ClaimStatus.ASSIGNED,
            user=self.admin_user,
            remarks='Surveyor assigned for preliminary inspection',
            request=request
        )

        claim.refresh_from_db()
        self.assertEqual(claim.status, ClaimStatus.ASSIGNED)

        # Verify ClaimStatusHistory
        history = ClaimStatusHistory.objects.filter(claim=claim).first()
        self.assertIsNotNone(history)
        self.assertEqual(history.old_status, ClaimStatus.NEW)
        self.assertEqual(history.new_status, ClaimStatus.ASSIGNED)
        self.assertEqual(history.changed_by, self.admin_user)
        self.assertEqual(history.remarks, 'Surveyor assigned for preliminary inspection')

        # Verify AuditLog
        audit = AuditLog.objects.filter(
            action='CLAIM_STATUS_TRANSITION',
            object_id=str(claim.pk)
        ).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.ip_address, '192.168.1.50')
        self.assertIn('NEW to ASSIGNED', audit.description)

    def test_skipping_ahead_transition_allowed(self):
        claim = self._create_sample_claim()
        # NEW -> ASSIGNED
        transition_claim_status(claim, ClaimStatus.ASSIGNED, self.admin_user)
        # ASSIGNED -> DOCUMENT_COLLECTION (skipping inspection pending/completed directly to doc collection)
        transition_claim_status(claim, ClaimStatus.DOCUMENT_COLLECTION, self.admin_user)
        claim.refresh_from_db()
        self.assertEqual(claim.status, ClaimStatus.DOCUMENT_COLLECTION)

    def test_invalid_status_transition_raises_validation_error(self):
        claim = self._create_sample_claim()
        # Cannot jump from NEW directly to CLOSED
        with self.assertRaises(ValidationError) as ctx:
            transition_claim_status(claim, ClaimStatus.CLOSED, self.admin_user)
        self.assertIn('Invalid status transition', str(ctx.exception))

        # Direct jump from CLOSED back to NEW must fail
        claim.status = ClaimStatus.CLOSED
        claim.save()
        with self.assertRaises(ValidationError) as ctx:
            transition_claim_status(claim, ClaimStatus.NEW, self.admin_user)
        self.assertIn('Invalid status transition', str(ctx.exception))

    def test_same_status_transition_raises_validation_error(self):
        claim = self._create_sample_claim()
        with self.assertRaises(ValidationError) as ctx:
            transition_claim_status(claim, ClaimStatus.NEW, self.admin_user)
        self.assertIn('already in status', str(ctx.exception))


class FullAPITests(TestCase):
    def setUp(self):
        from rest_framework.test import APIClient
        from rest_framework_simplejwt.tokens import RefreshToken
        from documents.models import DocumentType

        self.client = APIClient()
        self.admin = User.objects.create_user(
            username='api_admin',
            email='admin@test.com',
            password='password123',
            role=User.Role.ADMIN
        )
        self.surveyor_a = User.objects.create_user(
            username='api_surveyor_a',
            email='surv_a@test.com',
            password='password123',
            role=User.Role.SURVEYOR
        )
        self.surveyor_b = User.objects.create_user(
            username='api_surveyor_b',
            email='surv_b@test.com',
            password='password123',
            role=User.Role.SURVEYOR
        )

        self.admin_token = str(RefreshToken.for_user(self.admin).access_token)
        self.surveyor_a_token = str(RefreshToken.for_user(self.surveyor_a).access_token)
        self.surveyor_b_token = str(RefreshToken.for_user(self.surveyor_b).access_token)

        self.survey_type = SurveyType.objects.get(code='FIRE')
        self.doc_type, _ = DocumentType.objects.get_or_create(code='CLAIM_FORM', defaults={'name': 'Claim Form'})

        # Create basic insurer, insured, policy
        self.insurer = Insurer.objects.create(
            company_name='Star Insurance',
            branch_name='Central',
            address='Street 1',
            city='Mumbai',
            state='MH',
            pincode='400001',
            contact_person='Mr. Star',
            phone='1234567890',
            email='star@insure.test'
        )
        self.insured = Insured.objects.create(
            name='ABC Logistics',
            address='Street 2',
            city='Mumbai',
            state='MH',
            pincode='400001',
            phone='9876543210',
            email='abc@cargo.test'
        )
        now = timezone.now()
        self.policy = Policy.objects.create(
            insurer=self.insurer,
            policy_number='POL-001',
            policy_type='Fire Policy',
            start_datetime=now,
            end_datetime=now + timezone.timedelta(days=300),
            sum_insured=Decimal('1000000.00'),
            excess=Decimal('10000.00'),
            commodity='Warehouse Goods',
            subject_matter='Stocks'
        )

        self.claim = Claim.objects.create(
            survey_type=self.survey_type,
            insurer=self.insurer,
            insured=self.insured,
            policy=self.policy,
            instruction_date=date(2026, 9, 1),
            instruction_source='Email',
            date_of_loss=date(2026, 8, 30),
            nature_of_loss='Fire outbreak in main shed',
            loss_location='Warehouse 4',
            claimed_amount=Decimal('500000.00'),
            created_by=self.admin
        )

    def auth(self, token):
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

    def test_master_endpoints(self):
        self.auth(self.admin_token)
        # Survey Types
        resp = self.client.get('/api/survey-types/')
        self.assertEqual(resp.status_code, 200)

        # Insurers GET/POST/PATCH
        resp = self.client.get('/api/insurers/')
        self.assertEqual(resp.status_code, 200)
        resp = self.client.post('/api/insurers/', {
            'company_name': 'New Insurer',
            'branch_name': 'North',
            'address': 'Add',
            'city': 'Delhi',
            'state': 'DL',
            'pincode': '110001',
            'contact_person': 'P',
            'phone': '111',
            'email': 'n@ins.test'
        })
        self.assertEqual(resp.status_code, 201)
        ins_id = resp.data['id']
        resp = self.client.patch(f'/api/insurers/{ins_id}/', {'branch_name': 'North Updated'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['branch_name'], 'North Updated')

        # Insured GET/POST/PATCH
        resp = self.client.post('/api/insured/', {
            'name': 'New Client',
            'contact_person': 'Robert Green',
            'address': 'Add',
            'city': 'Delhi',
            'state': 'DL',
            'pincode': '110001',
            'phone': '222',
            'email': 'c@test.com'
        })
        self.assertEqual(resp.status_code, 201)
        insured_id = resp.data['id']
        resp = self.client.patch(f'/api/insured/{insured_id}/', {'name': 'Client Updated'})
        self.assertEqual(resp.status_code, 200)

        # Policies GET/POST/PATCH
        now = timezone.now()
        resp = self.client.post('/api/policies/', {
            'insurer': self.insurer.id,
            'policy_number': 'POL-002',
            'policy_type': 'Fire',
            'start_datetime': now.isoformat(),
            'end_datetime': (now + timezone.timedelta(days=100)).isoformat(),
            'sum_insured': '200000.00',
            'excess': '5000.00',
            'commodity': 'Wood',
            'subject_matter': 'Inventory'
        })
        self.assertEqual(resp.status_code, 201)
        pol_id = resp.data['id']
        resp = self.client.patch(f'/api/policies/{pol_id}/', {'sum_insured': '250000.00'})
        self.assertEqual(resp.status_code, 200)

    def test_claim_assign_and_reassign_workflow(self):
        self.auth(self.admin_token)

        # 1. Assign Surveyor A
        resp = self.client.post(f'/api/claims/{self.claim.id}/assign-surveyor/', {
            'surveyor': self.surveyor_a.id,
            'due_date': '2026-09-30',
            'priority': 'HIGH',
            'instructions': 'Inspect fire site promptly'
        })
        self.assertEqual(resp.status_code, 201)
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, ClaimStatus.ASSIGNED)

        # Surveyor A can now access claim
        self.auth(self.surveyor_a_token)
        resp_a = self.client.get(f'/api/claims/{self.claim.id}/')
        self.assertEqual(resp_a.status_code, 200)
        self.assertEqual(resp_a.data['assigned_surveyor_name'], self.surveyor_a.username)

        # Surveyor B cannot access claim
        self.auth(self.surveyor_b_token)
        resp_b = self.client.get(f'/api/claims/{self.claim.id}/')
        self.assertIn(resp_b.status_code, [403, 404])

        # 2. Reassign to Surveyor B
        self.auth(self.admin_token)
        resp_reassign = self.client.post(f'/api/claims/{self.claim.id}/reassign-surveyor/', {
            'surveyor': self.surveyor_b.id,
            'due_date': '2026-10-05',
            'priority': 'HIGH',
            'instructions': 'Taking over from Surveyor A',
            'remarks': 'Surveyor A unavailable'
        })
        self.assertEqual(resp_reassign.status_code, 200)

        # Old assignment must be REASSIGNED
        old_assignment = SurveyAssignment.objects.get(claim=self.claim, surveyor=self.surveyor_a)
        self.assertEqual(old_assignment.status, SurveyAssignment.Status.REASSIGNED)

        # Surveyor A now blocked
        self.auth(self.surveyor_a_token)
        resp_a_blocked = self.client.get(f'/api/claims/{self.claim.id}/')
        self.assertIn(resp_a_blocked.status_code, [403, 404])

        # Surveyor B now has access
        self.auth(self.surveyor_b_token)
        resp_b_allowed = self.client.get(f'/api/claims/{self.claim.id}/')
        self.assertEqual(resp_b_allowed.status_code, 200)

    def test_claim_subresources_and_assessment_recalculation(self):
        # Assign Surveyor B
        SurveyAssignment.objects.create(
            claim=self.claim,
            surveyor=self.surveyor_b,
            assigned_by=self.admin,
            due_date=date(2026, 9, 30),
            status=SurveyAssignment.Status.ASSIGNED
        )
        self.auth(self.surveyor_b_token)

        # 1. Inspection GET/POST and PATCH
        resp = self.client.post(f'/api/claims/{self.claim.id}/inspections/', {
            'inspection_date': '2026-09-12',
            'start_time': '10:00:00',
            'end_time': '12:00:00',
            'location': 'Site A',
            'person_contacted': 'Manager John',
            'contact_number': '1234567890'
        })
        self.assertEqual(resp.status_code, 201)
        insp_id = resp.data['id']

        resp = self.client.get(f'/api/claims/{self.claim.id}/inspections/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 1)

        resp = self.client.patch(f'/api/inspections/{insp_id}/', {'observations': 'Roof burnt'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['observations'], 'Roof burnt')

        # 2. Document Requirement GET/POST and PATCH
        resp = self.client.post(f'/api/claims/{self.claim.id}/requirements/', {
            'description': 'Fire Brigade Report',
            'requested_date': '2026-09-12',
            'requested_from': 'INSURED'
        })
        self.assertEqual(resp.status_code, 201)
        req_id = resp.data['id']

        resp = self.client.patch(f'/api/requirements/{req_id}/', {'status': 'RECEIVED'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['status'], 'RECEIVED')

        # 3. Assessment GET/POST/PATCH with Recalculation
        # Gross = 2 * 10000 = 20000
        # Underinsurance 10% = 2000
        # Salvage = 1000
        # Depreciation = 500
        # Adjusted = 20000 - 1000 - 2000 - 500 = 16500
        # Excess = 1000, Other deductions = 500
        # Net = 16500 - 1000 - 500 = 15000
        resp = self.client.post(f'/api/claims/{self.claim.id}/assessment/', {
            'salvage_amount': '1000.00',
            'underinsurance_percentage': '10.00',
            'depreciation_amount': '500.00',
            'policy_excess': '1000.00',
            'other_deductions': '500.00',
            'items': [
                {
                    'description': 'Damaged timber beams',
                    'quantity': '2.00',
                    'rate': '10000.00',
                    'claimed_amount': '25000.00'
                }
            ]
        }, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(Decimal(str(resp.data['gross_assessed_loss'])), Decimal('20000.00'))
        self.assertEqual(Decimal(str(resp.data['underinsurance_amount'])), Decimal('2000.00'))
        self.assertEqual(Decimal(str(resp.data['adjusted_loss'])), Decimal('16500.00'))
        self.assertEqual(Decimal(str(resp.data['net_assessed_loss'])), Decimal('15000.00'))

        assessment_id = resp.data['id']

        # PATCH /api/assessments/{id}/
        resp_patch = self.client.patch(f'/api/assessments/{assessment_id}/', {
            'salvage_amount': '2000.00'
        }, format='json')
        self.assertEqual(resp_patch.status_code, 200)
        # Net should now be 14000.00
        self.assertEqual(Decimal(str(resp_patch.data['net_assessed_loss'])), Decimal('14000.00'))

    def test_status_transition_endpoints(self):
        from reports.models import FSR, ReportStatus

        # Claim starts NEW -> ASSIGNED
        self.auth(self.admin_token)
        resp_assign = self.client.post(f'/api/claims/{self.claim.id}/assign-surveyor/', {
            'surveyor': self.surveyor_b.id,
            'due_date': '2026-09-30'
        })
        self.assertEqual(resp_assign.status_code, 201)
        self.claim.refresh_from_db()
        self.auth(self.surveyor_b_token)

        # Transition to INSPECTION_COMPLETED -> FSR_PREPARED
        transition_claim_status(self.claim, ClaimStatus.INSPECTION_COMPLETED, self.surveyor_b)
        transition_claim_status(self.claim, ClaimStatus.FSR_PREPARED, self.surveyor_b, remarks="Fast-track direct FSR")

        # Create an FSR in DRAFT
        fsr = FSR.objects.create(
            claim=self.claim,
            report_number='FSR-STATUS-001',
            report_date=date(2026, 9, 20),
            status=ReportStatus.DRAFT,
            prepared_by=self.surveyor_b,
            introduction='FSR Intro',
            occurrence_details='Occ Details',
            survey_details='Survey Details',
            extent_of_loss='Extent',
            cause_of_loss='Cause',
            value_at_risk=Decimal('1000000.00'),
            sum_insured=Decimal('1000000.00'),
            insured_claim_description='Desc',
            admissibility='Admissible',
            policy_coverage='Coverage',
            final_opinion='Opinion'
        )

        # 1. submit-report
        resp = self.client.post(f'/api/claims/{self.claim.id}/submit-report/', {'remarks': 'Final report submitted'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['status'], ClaimStatus.REPORT_SUBMITTED)
        fsr.refresh_from_db()
        self.assertEqual(fsr.status, ReportStatus.SUBMITTED)
        self.assertIsNotNone(fsr.submitted_at)

        # 2. raise-query (e.g. from Admin/Insurer)
        self.auth(self.admin_token)
        resp = self.client.post(f'/api/claims/{self.claim.id}/raise-query/', {'remarks': 'Need additional bills'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['status'], ClaimStatus.QUERY_RAISED)
        fsr.refresh_from_db()
        self.assertEqual(fsr.status, ReportStatus.QUERY)

        # 3. respond-query
        self.auth(self.surveyor_b_token)
        resp = self.client.post(f'/api/claims/{self.claim.id}/respond-query/', {'remarks': 'Bills uploaded'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['status'], ClaimStatus.RESUBMITTED)
        fsr.refresh_from_db()
        self.assertEqual(fsr.status, ReportStatus.DRAFT)
        self.assertEqual(fsr.version_number, 2)

        # 4. close: must fail if no report is FINAL
        self.auth(self.admin_token)
        resp_fail_close = self.client.post(f'/api/claims/{self.claim.id}/close/', {'remarks': 'Try close'})
        self.assertEqual(resp_fail_close.status_code, 400)
        self.assertIn('FINAL', str(resp_fail_close.data))

        # Mark report as FINAL and re-attempt close
        fsr.status = ReportStatus.FINAL
        fsr.save(update_fields=['status'])

        resp = self.client.post(f'/api/claims/{self.claim.id}/close/', {'remarks': 'Settlement complete'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['status'], ClaimStatus.CLOSED)

    def test_documents_and_reports_endpoints(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from documents.models import ClaimDocument

        # Assign Surveyor B
        SurveyAssignment.objects.create(
            claim=self.claim,
            surveyor=self.surveyor_b,
            assigned_by=self.admin,
            due_date=date(2026, 9, 30),
            status=SurveyAssignment.Status.ASSIGNED
        )
        self.auth(self.surveyor_b_token)

        # 1. Documents: POST /api/claims/{id}/documents/ and DELETE /api/documents/{id}/
        sample_pdf = SimpleUploadedFile("claim_doc.pdf", b"%PDF-1.4 test document", content_type="application/pdf")
        resp_doc = self.client.post(
            f'/api/claims/{self.claim.id}/documents/',
            {
                'document_type': self.doc_type.id,
                'file': sample_pdf,
                'document_number': 'DOC-991',
                'description': 'Claim submission copy'
            },
            format='multipart'
        )
        self.assertEqual(resp_doc.status_code, 201)
        doc_id = resp_doc.data['id']

        # GET /api/claims/{id}/documents/
        resp_docs_list = self.client.get(f'/api/claims/{self.claim.id}/documents/')
        self.assertEqual(resp_docs_list.status_code, 200)
        self.assertEqual(len(resp_docs_list.data), 1)

        # DELETE /api/documents/{id}/
        resp_del = self.client.delete(f'/api/documents/{doc_id}/')
        self.assertEqual(resp_del.status_code, 204)
        self.assertFalse(ClaimDocument.objects.filter(id=doc_id).exists())

        # 2. ILA Report: POST /api/claims/{id}/ila/ and GET /api/claims/{id}/ila/
        resp_ila = self.client.post(f'/api/claims/{self.claim.id}/ila/', {
            'report_number': 'ILA-2026-001',
            'report_date': '2026-09-12',
            'instruction_date': '2026-09-01',
            'instruction_source': 'Insurer Email',
            'visit_date': '2026-09-02',
            'visit_start_time': '10:00:00',
            'visit_end_time': '12:00:00',
            'inspection_location': 'Main Warehouse',
            'person_contacted': 'Plant Head',
            'contact_number': '9876543210',
            'policy_number': 'POL-001',
            'policy_type': 'Fire Policy',
            'commodity': 'Goods',
            'sum_insured': '1000000.00',
            'policy_excess': '10000.00',
            'survey_and_inspection': 'Joint inspection completed',
            'extent_of_damage': 'Damage to storage area',
            'cause_of_damage': 'Electrical short circuit',
            'salvage_prospect': 'Minimal',
            'estimated_loss': '300000.00',
            'claimed_amount': '500000.00',
            'policy_liability': 'Admissible prima facie',
            'budgetary_reserve': '350000.00'
        })
        self.assertEqual(resp_ila.status_code, 201)
        resp_ila_get = self.client.get(f'/api/claims/{self.claim.id}/ila/')
        self.assertEqual(resp_ila_get.status_code, 200)
        self.assertEqual(len(resp_ila_get.data), 1)

        # 3. ISR Report: POST /api/claims/{id}/isr/ and GET /api/claims/{id}/isr/
        resp_isr = self.client.post(f'/api/claims/{self.claim.id}/isr/', {
            'report_number': 'ISR-2026-001',
            'report_date': '2026-09-15',
            'introduction': 'Interim report on warehouse fire',
            'occurrence_details': 'Fire reported on Aug 30',
            'survey_details': 'Inspection done on Sept 2',
            'extent_of_damage': 'Partial stock loss',
            'cause_of_loss': 'Short circuit',
            'initial_assessment': 'Estimated at Rs 3,00,000',
            'policy_liability': 'Policy terms are applicable'
        })
        self.assertEqual(resp_isr.status_code, 201)
        resp_isr_get = self.client.get(f'/api/claims/{self.claim.id}/isr/')
        self.assertEqual(resp_isr_get.status_code, 200)
        self.assertEqual(len(resp_isr_get.data), 1)

        # 4. FSR Report: POST /api/claims/{id}/fsr/ and GET /api/claims/{id}/fsr/
        resp_fsr = self.client.post(f'/api/claims/{self.claim.id}/fsr/', {
            'report_number': 'FSR-2026-001',
            'report_date': '2026-09-20',
            'introduction': 'Final Survey Report',
            'occurrence_details': 'Loss occurred at warehouse',
            'survey_details': 'Detailed survey conducted',
            'extent_of_loss': 'Finalized stock loss',
            'cause_of_loss': 'Electrical short circuit confirmed',
            'value_at_risk': '1200000.00',
            'sum_insured': '1000000.00',
            'underinsurance_percentage': '16.67',
            'salvage_description': 'Burnt remnants',
            'salvage_amount': '5000.00',
            'insured_claim_description': 'Stocks damaged by fire',
            'admissibility': 'Claim is admissible',
            'policy_coverage': 'Fire standard policy',
            'final_opinion': 'Recommend settlement as per assessment'
        })
        self.assertEqual(resp_fsr.status_code, 201)
        resp_fsr_get = self.client.get(f'/api/claims/{self.claim.id}/fsr/')
        self.assertEqual(resp_fsr_get.status_code, 200)
        self.assertEqual(len(resp_fsr_get.data), 1)
        self.assertIn('disclaimer_note', resp_fsr.data)


class ClaimServicesUnitTests(TestCase):
    def setUp(self):
        from claims.services import (
            assign_surveyor,
            reassign_surveyor,
            submit_report,
            raise_query,
            respond_query,
            close_claim,
        )
        from reports.models import FSR, ReportStatus

        self.admin = User.objects.create_user(
            username='srv_admin',
            email='admin@srv.test',
            password='password123',
            role=User.Role.ADMIN
        )
        self.surveyor_a = User.objects.create_user(
            username='srv_surveyor_a',
            email='surv_a@srv.test',
            password='password123',
            role=User.Role.SURVEYOR
        )
        self.surveyor_b = User.objects.create_user(
            username='srv_surveyor_b',
            email='surv_b@srv.test',
            password='password123',
            role=User.Role.SURVEYOR
        )

        survey_type = SurveyType.objects.get(code='FIRE')
        insurer = Insurer.objects.create(
            company_name='Service Insurer',
            branch_name='HQ',
            address='Addr',
            city='City',
            state='State',
            pincode='123456',
            contact_person='CP',
            phone='1234567890',
            email='ins@srv.test'
        )
        insured = Insured.objects.create(
            name='Service Insured',
            contact_person='Contact',
            address='Addr',
            city='City',
            state='State',
            pincode='123456',
            phone='9876543210',
            email='insured@srv.test'
        )
        now = timezone.now()
        policy = Policy.objects.create(
            insurer=insurer,
            policy_number='POL-SRV-01',
            policy_type='Fire Policy',
            start_datetime=now,
            end_datetime=now + timezone.timedelta(days=365),
            sum_insured=Decimal('500000.00'),
            excess=Decimal('5000.00'),
            commodity='Goods',
            subject_matter='Stocks'
        )
        self.claim = Claim.objects.create(
            survey_type=survey_type,
            insurer=insurer,
            insured=insured,
            policy=policy,
            instruction_date=date(2026, 9, 1),
            instruction_source='Email',
            date_of_loss=date(2026, 8, 30),
            nature_of_loss='Fire',
            loss_location='Godown 1',
            claimed_amount=Decimal('200000.00'),
            created_by=self.admin
        )

    def test_assign_and_reassign_surveyor_services(self):
        from claims.services import assign_surveyor, reassign_surveyor

        # 1. Assign Surveyor A: should transition claim to ASSIGNED
        assignment_a = assign_surveyor(
            claim=self.claim,
            surveyor=self.surveyor_a,
            assigned_by=self.admin,
            due_date=date(2026, 9, 20),
            instructions='Inspect quickly'
        )
        self.assertEqual(assignment_a.status, SurveyAssignment.Status.ASSIGNED)
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, ClaimStatus.ASSIGNED)

        # Advance claim to INSPECTION_PENDING
        transition_claim_status(self.claim, ClaimStatus.INSPECTION_PENDING, self.surveyor_a)
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, ClaimStatus.INSPECTION_PENDING)

        # 2. Reassign to Surveyor B:
        # Closes out Surveyor A's assignment as REASSIGNED, creates Surveyor B assignment.
        # Deliberately does NOT transition claim status back to ASSIGNED!
        assignment_b = reassign_surveyor(
            claim=self.claim,
            new_surveyor=self.surveyor_b,
            assigned_by=self.admin,
            due_date=date(2026, 9, 25),
            remarks='Surveyor A on emergency leave'
        )
        assignment_a.refresh_from_db()
        self.assertEqual(assignment_a.status, SurveyAssignment.Status.REASSIGNED)
        self.assertEqual(assignment_b.status, SurveyAssignment.Status.ASSIGNED)

        self.claim.refresh_from_db()
        # Status remains INSPECTION_PENDING - no backward jump!
        self.assertEqual(self.claim.status, ClaimStatus.INSPECTION_PENDING)

    def test_report_lifecycle_services(self):
        from claims.services import assign_surveyor, submit_report, raise_query, respond_query, close_claim
        from reports.models import FSR, ReportStatus

        assign_surveyor(self.claim, self.surveyor_b, self.admin)
        transition_claim_status(self.claim, ClaimStatus.INSPECTION_COMPLETED, self.surveyor_b)
        transition_claim_status(self.claim, ClaimStatus.FSR_PREPARED, self.surveyor_b, remarks="Direct FSR expedited")

        fsr = FSR.objects.create(
            claim=self.claim,
            report_number='FSR-SRV-001',
            report_date=date(2026, 9, 22),
            status=ReportStatus.DRAFT,
            prepared_by=self.surveyor_b,
            introduction='Intro',
            occurrence_details='Occ',
            survey_details='Survey',
            extent_of_loss='Loss',
            cause_of_loss='Fire',
            value_at_risk=Decimal('500000.00'),
            sum_insured=Decimal('500000.00'),
            insured_claim_description='Claim',
            admissibility='Admissible',
            policy_coverage='Coverage',
            final_opinion='Opinion'
        )

        # 1. submit_report
        submit_report(self.claim, fsr, self.surveyor_b)
        fsr.refresh_from_db()
        self.assertEqual(fsr.status, ReportStatus.SUBMITTED)
        self.assertIsNotNone(fsr.submitted_at)
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, ClaimStatus.REPORT_SUBMITTED)

        # Cannot submit already submitted report
        with self.assertRaises(ValidationError):
            submit_report(self.claim, fsr, self.surveyor_b)

        # 2. raise_query
        raise_query(self.claim, self.admin, remarks='Missing fire brigade report')
        fsr.refresh_from_db()
        self.assertEqual(fsr.status, ReportStatus.QUERY)
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, ClaimStatus.QUERY_RAISED)

        # 3. respond_query
        respond_query(self.claim, fsr, self.surveyor_b, remarks='Attached fire report')
        fsr.refresh_from_db()
        self.assertEqual(fsr.status, ReportStatus.DRAFT)
        self.assertEqual(fsr.version_number, 2)
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, ClaimStatus.RESUBMITTED)

        # 4. close_claim fails if no report is FINAL
        with self.assertRaises(ValidationError) as ctx:
            close_claim(self.claim, self.admin)
        self.assertIn('FINAL', str(ctx.exception))

        # Mark report as FINAL and close
        fsr.status = ReportStatus.FINAL
        fsr.save()
        close_claim(self.claim, self.admin, remarks='All queries addressed, closed.')
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, ClaimStatus.CLOSED)



