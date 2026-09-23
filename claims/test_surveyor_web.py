from datetime import date, time
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.utils import timezone
from surveys.models import SurveyType, Inspection
from claims.models import (
    Insurer, Insured, Policy, Claim, ClaimStatus, SurveyAssignment, Priority, ClaimStatusHistory
)
from claims.services import assign_surveyor, transition_claim_status
from reports.models import AuditLog, ILA, ISR, FSR, ReportStatus
from reports.services import save_report_pdf_as_document

User = get_user_model()


class SurveyorWebViewsTests(TestCase):
    def setUp(self):
        self.client = Client()

        # Users
        self.admin = User.objects.create_user(
            username='admin_web',
            email='admin@web.test',
            password='password123',
            role=User.Role.ADMIN
        )
        self.surveyor_a = User.objects.create_user(
            username='surveyor_a',
            email='surveyora@web.test',
            password='password123',
            role=User.Role.SURVEYOR
        )
        self.surveyor_b = User.objects.create_user(
            username='surveyor_b',
            email='surveyorb@web.test',
            password='password123',
            role=User.Role.SURVEYOR
        )

        # Master & Claim Data
        self.survey_type = SurveyType.objects.get(code='FIRE')
        self.insurer = Insurer.objects.create(
            company_name='Apex General Insurance',
            branch_name='North Sector',
            address='100 Corporate Way',
            city='Metro City',
            state='State',
            pincode='100001',
            contact_person='David Miller',
            phone='+1-555-1234',
            email='claims@apex.test'
        )
        self.insured = Insured.objects.create(
            name='Precision Components Ltd',
            company_name='Precision Group',
            address='Ind Zone 5',
            city='Metro City',
            state='State',
            pincode='100002',
            phone='+1-555-5678',
            email='contact@precision.test',
            contact_person='Robert Chen'
        )
        now = timezone.now()
        self.policy = Policy.objects.create(
            insurer=self.insurer,
            policy_number='POL-WEB-2026-01',
            policy_type='Fire & Perils',
            start_datetime=now,
            end_datetime=now + timezone.timedelta(days=365),
            sum_insured=Decimal('1000000.00'),
            excess=Decimal('5000.00'),
            commodity='Industrial Machinery',
            subject_matter='Factory Plant',
            remarks='Standard coverage'
        )

        # Create Claim
        self.claim = Claim.objects.create(
            claim_number='CLM-WEB-001',
            survey_type=self.survey_type,
            insurer=self.insurer,
            insured=self.insured,
            policy=self.policy,
            instruction_date=date(2026, 9, 15),
            instruction_source='Regional Manager',
            date_of_loss=date(2026, 9, 14),
            nature_of_loss='Fire outbreak in workshop',
            loss_location='Workshop 2, Sector 12',
            claimed_amount=Decimal('250000.00'),
            priority=Priority.HIGH,
            status=ClaimStatus.NEW,
            created_by=self.admin
        )

    def test_surveyor_dashboard_access_and_tile_counts(self):
        """Test surveyor dashboard access control and accurate status mapping."""
        # Unauthenticated redirects to login
        response = self.client.get('/dashboard/surveyor/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

        # Admin user gets 403 Forbidden
        self.client.login(username='admin_web', password='password123')
        admin_response = self.client.get('/dashboard/surveyor/')
        self.assertEqual(admin_response.status_code, 403)
        self.client.logout()

        # Assign surveyor_a to the claim
        assign_surveyor(self.claim, self.surveyor_a, self.admin)
        # Advance claim to INSPECTION_COMPLETED (Pending ILA)
        transition_claim_status(self.claim, ClaimStatus.INSPECTION_PENDING, self.surveyor_a)
        transition_claim_status(self.claim, ClaimStatus.INSPECTION_COMPLETED, self.surveyor_a)

        # Create an inspection today for surveyor_a
        today = timezone.localdate()
        Inspection.objects.create(
            claim=self.claim,
            surveyor=self.surveyor_a,
            inspection_date=today,
            start_time=time(10, 0),
            end_time=time(12, 0),
            location='Workshop 2',
            person_contacted='Robert Chen',
            contact_number='+1-555-5678'
        )

        # Surveyor A logs in
        self.client.login(username='surveyor_a', password='password123')
        resp = self.client.get('/dashboard/surveyor/')
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'dashboard/surveyor_dashboard.html')

        # Verify tile counts in context
        tiles = {t['title']: t['count'] for t in resp.context['tiles']}
        self.assertEqual(tiles['My Assigned Claims'], 1)
        self.assertEqual(tiles["Today's Inspections"], 1)
        self.assertEqual(tiles['Pending ILA'], 1)
        self.assertEqual(tiles['Pending LOR'], 0)
        self.assertEqual(tiles['Pending Documents'], 0)
        self.assertEqual(tiles['Pending Assessment'], 0)
        self.assertEqual(tiles['Pending ISR'], 0)
        self.assertEqual(tiles['Pending FSR'], 0)
        self.assertEqual(tiles['Completed'], 0)

        # Table shows the claim
        self.assertContains(resp, 'CLM-WEB-001')

    def test_claim_detail_permission_denied_for_unassigned_surveyor(self):
        """Unassigned surveyor gets 403 PermissionDenied when accessing /claims/<id>/."""
        # Assign claim to surveyor_a
        assign_surveyor(self.claim, self.surveyor_a, self.admin)

        # Surveyor B (not assigned) tries to access claim detail
        self.client.login(username='surveyor_b', password='password123')
        resp = self.client.get(f'/claims/{self.claim.id}/')
        self.assertEqual(resp.status_code, 403)

        # Surveyor A (assigned) gets 200 OK
        self.client.login(username='surveyor_a', password='password123')
        resp_a = self.client.get(f'/claims/{self.claim.id}/')
        self.assertEqual(resp_a.status_code, 200)
        self.assertContains(resp_a, 'CLM-WEB-001')

        # Admin gets 200 OK
        self.client.login(username='admin_web', password='password123')
        resp_admin = self.client.get(f'/claims/{self.claim.id}/')
        self.assertEqual(resp_admin.status_code, 200)

    def test_claim_detail_all_13_tabs_render(self):
        """Verify that all 13 workspace tabs render without error."""
        assign_surveyor(self.claim, self.surveyor_a, self.admin)
        self.client.login(username='surveyor_a', password='password123')

        tabs = [
            'overview', 'assignment', 'policy', 'inspection', 'ila',
            'lor', 'documents', 'photos', 'invoices', 'assessment',
            'isr', 'fsr', 'activity'
        ]
        for tab in tabs:
            resp = self.client.get(f'/claims/{self.claim.id}/?tab={tab}')
            self.assertEqual(resp.status_code, 200, f"Tab '{tab}' failed to render.")
            self.assertEqual(resp.context['active_tab'], tab)
            self.assertContains(resp, f'?tab={tab}')

    def test_surveyor_assignment_and_pdf_generation_audit_in_activity_tab(self):
        """
        Crucial check requested by user:
        Assert that both a surveyor-assignment audit entry and a PDF-generation audit entry
        both appear on a claim's Activity tab with the new claim FK linkage.
        """
        # 1. Assign surveyor to claim (triggers AuditLog for SurveyAssignment with claim FK)
        assignment = assign_surveyor(
            self.claim,
            self.surveyor_a,
            self.admin,
            instructions="Complete inspection promptly"
        )

        # 2. Advance to ILA and generate PDF (triggers AuditLog for PDF generation with claim FK)
        transition_claim_status(self.claim, ClaimStatus.INSPECTION_PENDING, self.surveyor_a)
        transition_claim_status(self.claim, ClaimStatus.INSPECTION_COMPLETED, self.surveyor_a)

        ila = ILA.objects.create(
            claim=self.claim,
            report_number='ILA-ACT-TEST-001',
            report_date=date(2026, 9, 16),
            status=ReportStatus.DRAFT,
            version_number=1,
            prepared_by=self.surveyor_a,
            instruction_date=date(2026, 9, 15),
            instruction_source='Regional Office',
            surveyor=self.surveyor_a,
            visit_date=date(2026, 9, 16),
            visit_start_time=time(10, 0),
            visit_end_time=time(12, 0),
            inspection_location='Industrial Area Phase 2',
            person_contacted='Site Manager',
            contact_number='+1-555-9999',
            policy_number='POL-WEB-2026-01',
            policy_type='Fire & Perils',
            commodity='Plant & Machinery',
            sum_insured=Decimal('1000000.00'),
            policy_excess=Decimal('5000.00'),
            survey_and_inspection='Inspected damaged machinery on site',
            extent_of_damage='Heavy fire damage to production line',
            cause_of_damage='Electrical short circuit',
            salvage_prospect='Scrap metal only',
            estimated_loss=Decimal('350000.00'),
            claimed_amount=Decimal('400000.00'),
            policy_liability='Admissible under Fire Section',
            budgetary_reserve=Decimal('350000.00')
        )

        # Generate report PDF and save as document (creates ClaimDocument and AuditLog)
        save_report_pdf_as_document(ila, user=self.surveyor_a)

        # Verify DB audit logs exist linked to this claim
        claim_audit_logs = AuditLog.objects.filter(claim=self.claim)
        assignment_logs = claim_audit_logs.filter(model_name='SurveyAssignment')
        pdf_logs = claim_audit_logs.filter(action__icontains='PDF')
        
        self.assertTrue(assignment_logs.exists(), "No AuditLog found for SurveyAssignment linked to claim.")
        self.assertTrue(pdf_logs.exists(), "No AuditLog found for PDF generation linked to claim.")

        # 3. Access Activity tab on claim detail page
        self.client.login(username='surveyor_a', password='password123')
        resp = self.client.get(f'/claims/{self.claim.id}/?tab=activity')
        self.assertEqual(resp.status_code, 200)

        # Assert surveyor-assignment and PDF-generation events both appear in rendered Activity tab
        content = resp.content.decode('utf-8')
        self.assertIn('SurveyAssignment', content)
        self.assertIn('Report Pdf Generated', content)
        
        # Check timeline items in context
        titles = [item['title'] for item in resp.context['timeline_items']]
        self.assertTrue(any('SurveyAssignment' in t or 'Surveyor Assigned' in t for t in titles), f"Assignment not in titles: {titles}")
        self.assertTrue(any('Report Pdf Generated' in t for t in titles), f"PDF not in titles: {titles}")

    def test_fsr_prefill_from_submitted_isr_and_persistence_of_edits(self):
        """
        Creating an FSR for a claim with a submitted ISR pre-fills the 5 mapped fields
        and leaves remarks blank. Saving with edited values persists across tab reloads.
        """
        assign_surveyor(self.claim, self.surveyor_a, self.admin)
        self.client.login(username='surveyor_a', password='password123')

        # 1. When no ISR exists, FSR initial fields are blank
        resp = self.client.get(f'/claims/{self.claim.id}/?tab=fsr')
        self.assertEqual(resp.status_code, 200)
        form = resp.context['fsr_form']
        self.assertFalse(form.initial.get('introduction'))

        # 2. When an ISR exists but is still DRAFT, FSR initial fields remain blank
        isr = ISR.objects.create(
            claim=self.claim,
            report_number="ISR-2026-999",
            report_date=date(2026, 9, 20),
            status=ReportStatus.DRAFT,
            prepared_by=self.surveyor_a,
            introduction="Draft intro - should not be pulled",
            occurrence_details="Draft occurrence",
            survey_details="Draft survey",
            extent_of_damage="Draft damage",
            cause_of_loss="Draft cause",
            remarks="Draft remarks"
        )
        resp = self.client.get(f'/claims/{self.claim.id}/?tab=fsr')
        form = resp.context['fsr_form']
        self.assertFalse(form.initial.get('introduction'))

        # 3. When the ISR is SUBMITTED, opening FSR tab pre-fills the 5 mapped fields
        isr.status = ReportStatus.SUBMITTED
        isr.submitted_at = timezone.now()
        isr.introduction = "Official ISR Introduction"
        isr.occurrence_details = "Official Incident Occurrence Details"
        isr.survey_details = "Official On-Site Survey Details"
        isr.cause_of_loss = "Short circuit in power room"
        isr.extent_of_damage = "Heavy burn damage across panels A & B"
        isr.remarks = "Initial phase pending documentation"
        isr.save()

        resp = self.client.get(f'/claims/{self.claim.id}/?tab=fsr')
        form = resp.context['fsr_form']
        self.assertEqual(form.initial.get('introduction'), "Official ISR Introduction")
        self.assertEqual(form.initial.get('occurrence_details'), "Official Incident Occurrence Details")
        self.assertEqual(form.initial.get('survey_details'), "Official On-Site Survey Details")
        self.assertEqual(form.initial.get('cause_of_loss'), "Short circuit in power room")
        # Notice extent_of_damage mapped to extent_of_loss
        self.assertEqual(form.initial.get('extent_of_loss'), "Heavy burn damage across panels A & B")
        # Remarks must be left blank
        self.assertFalse(form.initial.get('remarks'))

        # 4. Surveyor edits values and saves FSR draft
        # Provide history for LOR & Assessment so skip justification is not needed
        ClaimStatusHistory.objects.create(claim=self.claim, old_status=ClaimStatus.ASSIGNED, new_status=ClaimStatus.LOR_ISSUED, changed_by=self.admin)
        ClaimStatusHistory.objects.create(claim=self.claim, old_status=ClaimStatus.LOR_ISSUED, new_status=ClaimStatus.ASSESSMENT_IN_PROGRESS, changed_by=self.admin)
        self.claim.status = ClaimStatus.ASSESSMENT_IN_PROGRESS
        self.claim.save()

        post_data = {
            'report_number': 'SSLA-91-F-F-260001',
            'report_date': '2026-09-22',
            'introduction': 'Surveyor Edited Introduction for Final Report',
            'occurrence_details': 'Official Incident Occurrence Details',
            'survey_details': 'Surveyor Edited Survey Findings',
            'extent_of_loss': 'Surveyor Finalized Loss Extent: Panel A totaled, Panel B salvaged',
            'cause_of_loss': 'Short circuit in power room',
            'value_at_risk': '1000000.00',
            'sum_insured': '1000000.00',
            'underinsurance_percentage': '0.00',
            'salvage_description': 'Metal scrap from Panel A',
            'salvage_amount': '5000.00',
            'insured_claim_description': 'Total replacement claimed',
            'admissibility': 'Admissible under Standard Fire Peril',
            'policy_coverage': 'Fire section applicable',
            'policy_exclusions': 'None',
            'breach_of_warranty': False,
            'warranty_details': '',
            'remarks': 'Final assessment notes by surveyor',
            'final_opinion': 'Claim recommended for settlement',
        }
        save_resp = self.client.post(
            f'/claims/{self.claim.id}/report/fsr/save/',
            data=post_data,
            follow=True
        )
        self.assertEqual(save_resp.status_code, 200)
        self.assertTrue(FSR.objects.filter(claim=self.claim).exists())

        # 5. Reload the FSR tab: must show surveyor's edited values, NOT the ISR's original values
        reload_resp = self.client.get(f'/claims/{self.claim.id}/?tab=fsr')
        self.assertEqual(reload_resp.status_code, 200)
        reloaded_form = reload_resp.context['fsr_form']
        self.assertIsNotNone(reloaded_form.instance.pk)
        self.assertEqual(reloaded_form.instance.introduction, 'Surveyor Edited Introduction for Final Report')
        self.assertEqual(reloaded_form.instance.extent_of_loss, 'Surveyor Finalized Loss Extent: Panel A totaled, Panel B salvaged')
        self.assertEqual(reloaded_form.instance.remarks, 'Final assessment notes by surveyor')

