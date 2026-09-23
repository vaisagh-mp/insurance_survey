from datetime import date, time
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.utils import timezone

from surveys.models import SurveyType
from claims.models import Insurer, Insured, Policy, Claim, ClaimStatus
from claims.services import transition_claim_status
from assessments.models import Assessment, AssessmentItem
from documents.models import DocumentType, ClaimDocument
from reports.models import ILA, FSR, ReportStatus
from reports.services import generate_report_pdf, save_report_pdf_as_document, get_soteria_assets

User = get_user_model()


class FSRFormatAndEnclosureTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin_fsr',
            email='admin@fsr.test',
            password='password123',
            role=User.Role.ADMIN
        )
        self.surveyor = User.objects.create_user(
            username='surveyor_fsr',
            email='surveyor@fsr.test',
            password='password123',
            role=User.Role.SURVEYOR
        )
        self.survey_type = SurveyType.objects.get(code='FIRE')
        self.insurer = Insurer.objects.create(
            company_name='National Insurance Co',
            branch_name='Mumbai Branch',
            address='Fort, Mumbai',
            city='Mumbai',
            state='Maharashtra',
            pincode='400001'
        )
        self.insured = Insured.objects.create(
            name='Precision Tech Ltd',
            company_name='Precision Group',
            address='MIDC Industrial Area',
            city='Navi Mumbai',
            state='Maharashtra',
            pincode='400703'
        )
        self.policy = Policy.objects.create(
            insurer=self.insurer,
            policy_number='POL-FSR-2026-001',
            policy_type='Standard Fire & Special Perils',
            start_datetime=timezone.now(),
            end_datetime=timezone.now() + timezone.timedelta(days=365),
            sum_insured=Decimal('5000000.00'),
            excess=Decimal('10000.00'),
            commodity='Plant & Machinery',
            subject_matter='Plant & Machinery'
        )
        self.claim = Claim.objects.create(
            claim_number='CLM-FSR-001',
            survey_type=self.survey_type,
            insurer=self.insurer,
            insured=self.insured,
            policy=self.policy,
            instruction_date=date(2026, 9, 10),
            instruction_source='Official Email Intimation',
            date_of_loss=date(2026, 9, 9),
            nature_of_loss='Fire in Electrical Control Room',
            loss_location='Turbhe, Navi Mumbai',
            claimed_amount=Decimal('450000.00'),
            status=ClaimStatus.NEW,
            created_by=self.admin
        )

    def test_fsr_pdf_soteria_format_and_document_enclosed(self):
        """
        Test FSR PDF template formatting:
        - adequacy_of_sum_insured is rendered under ADEQUACY OF SUM INSURED
        - AssessmentItem line-item table renders description, claimed, recommended, and remarks
        - Assessment financial breakdown renders with Total, Underinsurance, Adjusted Loss, Net Loss
        - Conditional policy_coverage and policy_exclusions omitted when empty, rendered when filled
        - Document Enclosed list rendered from verified documents and omitted when none exist
        """
        # Create Assessment with AssessmentItems
        assessment = Assessment.objects.create(
            claim=self.claim,
            gross_assessed_loss=Decimal('400000.00'),
            salvage_amount=Decimal('20000.00'),
            underinsurance_percentage=Decimal('10.00'),
            underinsurance_amount=Decimal('40000.00'),
            adjusted_loss=Decimal('340000.00'),
            policy_excess=Decimal('10000.00'),
            other_deductions=Decimal('5000.00'),
            net_assessed_loss=Decimal('325000.00'),
            created_by=self.surveyor
        )
        AssessmentItem.objects.create(
            assessment=assessment,
            description='Main Distribution Panel A',
            specification='ABB 415V Switchgear',
            quantity=Decimal('1.00'),
            rate=Decimal('250000.00'),
            claimed_amount=Decimal('280000.00'),
            assessed_amount=Decimal('250000.00'),
            remarks='Inventories as on 31st March 2025, per audited P&L'
        )
        AssessmentItem.objects.create(
            assessment=assessment,
            description='Sub-cables & Busbars',
            quantity=Decimal('1.00'),
            rate=Decimal('150000.00'),
            claimed_amount=Decimal('170000.00'),
            assessed_amount=Decimal('150000.00'),
            remarks='Recommended based on manufacturer quotation'
        )

        # Upload a verified ClaimDocument
        doc_type = DocumentType.objects.create(name='Police Panchanama', code='PANCHANAMA')
        ClaimDocument.objects.create(
            claim=self.claim,
            document_type=doc_type,
            document_number='FIR-9876',
            document_date=date(2026, 9, 10),
            description='Local police intimation panchanama',
            uploaded_by=self.admin,
            verified=True
        )

        # 1. FSR with empty policy_coverage and policy_exclusions
        fsr = FSR.objects.create(
            claim=self.claim,
            report_number='SSLA-91-F-F-261127',
            report_date=date(2026, 9, 22),
            introduction='In accordance with instructions received, we inspected...',
            occurrence_details='Fire broke out in the early morning...',
            survey_details='On site survey conducted on 11.09.2026...',
            extent_of_loss='Severe damage to Main Distribution Panel A...',
            cause_of_loss='Electrical arcing in busbar chamber...',
            adequacy_of_sum_insured='Balance sheet for FY 2024-25 shows fixed assets of Rs. 5.55 Cr against Sum Insured of Rs. 5.00 Cr. Underinsurance of 10% applies.',
            value_at_risk=Decimal('5555555.00'),
            sum_insured=Decimal('5000000.00'),
            underinsurance_percentage=Decimal('10.00'),
            salvage_amount=Decimal('20000.00'),
            salvage_description='Charred copper busbars retained by insured as scrap.',
            insured_claim_description='Insured claimed total replacement of switchgear.',
            admissibility='Loss is admissible under Fire Section Clause 1.',
            policy_coverage='',
            policy_exclusions='',
            breach_of_warranty=False,
            final_opinion='Loss is assessed at Net Rs. 3,25,000/- subject to policy terms.',
            remarks='Claim processed without prejudice.',
            assessment=assessment,
            prepared_by=self.surveyor,
            status=ReportStatus.DRAFT
        )

        pdf_bytes = generate_report_pdf(fsr)
        self.assertTrue(len(pdf_bytes) > 0)

        # Check template rendering directly to assert exact text presence and omission
        context = {
            'report': fsr,
            'claim': self.claim,
            'assessment': assessment,
            'assessment_items': list(assessment.items.all()),
            'total_after_salvage': assessment.gross_assessed_loss - assessment.salvage_amount,
            'enclosed_documents': list(self.claim.documents.filter(verified=True)),
            'company_email': 'opsmumbai@ssla.global',
            'company_website': 'www.ssla.global',
            'company_address': 'Navi Mumbai',
            'company_name': 'SOTERIA',
            'signatory_name': 'Gautam Acharyya',
            'signatory_designation': 'Principal Surveyor',
            'signatory_license': 'Corporate Survey License No: 200146',
        }
        html = render_to_string('reports/fsr_pdf.html', context)

        # Assert Page 1 Header (Corporate License, Claim Ref, Date, Insurer Address)
        self.assertIn('Corporate Survey Licence No.', html)
        self.assertIn('SLA 200146 EXP. DATE 15-05-2027', html)
        self.assertIn('Our Claim No: SSLA-91-F-F-261127', html)
        self.assertIn('Date: 22-09-2026', html)
        self.assertIn('National Insurance Co', html)
        self.assertIn('Mumbai Branch', html)
        self.assertIn('Fort, Mumbai', html)

        # Assert Section Order & Content
        self.assertIn('ADEQUACY OF SUM INSURED', html)
        self.assertIn('Balance sheet for FY 2024-25 shows fixed assets', html)
        self.assertIn('ASSESSMENT OF LOSS', html)
        self.assertIn('Main Distribution Panel A', html)
        self.assertIn('ABB 415V Switchgear', html)
        self.assertIn('Inventories as on 31st March 2025, per audited P&amp;L', html)
        self.assertIn('Sub-cables &amp; Busbars', html)
        self.assertIn('Recommended based on manufacturer quotation', html)
        self.assertIn('Gross Assessed Loss', html)
        self.assertIn('Less: Salvage', html)
        self.assertIn('Total', html)
        self.assertIn('Less: Underinsurance (10.00%)', html)
        self.assertIn('Adjusted Loss', html)
        self.assertIn('NET ASSESSED LOSS', html)

        # Empty coverage/exclusions must omit headings
        self.assertNotIn('<strong>POLICY COVERAGE:</strong>', html)
        self.assertNotIn('<strong>POLICY EXCLUSIONS:</strong>', html)

        # Document Enclosed list
        self.assertIn('DOCUMENTS ENCLOSED', html)
        self.assertIn('Police Panchanama', html)
        self.assertIn('FIR-9876', html)

        # 2. Filled policy_coverage and policy_exclusions must render headings
        fsr.policy_coverage = 'Standard Fire and Allied Perils Section II in force.'
        fsr.policy_exclusions = 'Exclusion 3: Terrorism Perils excluded.'
        fsr.save()
        context['report'] = fsr
        html_filled = render_to_string('reports/fsr_pdf.html', context)
        self.assertIn('<strong>POLICY COVERAGE:</strong>', html_filled)
        self.assertIn('Standard Fire and Allied Perils Section II in force.', html_filled)
        self.assertIn('<strong>POLICY EXCLUSIONS:</strong>', html_filled)
        self.assertIn('Exclusion 3: Terrorism Perils excluded.', html_filled)

        # 3. When no verified documents exist, DOCUMENTS ENCLOSED is omitted
        context['enclosed_documents'] = []
        html_no_docs = render_to_string('reports/fsr_pdf.html', context)
        self.assertNotIn('DOCUMENTS ENCLOSED', html_no_docs)

    def test_fsr_skip_ahead_instruction_details_without_ila(self):
        """
        A claim that transitions directly from INSPECTION_COMPLETED to FSR_PREPARED
        (no ILA ever created) renders instruction details directly from claim.instruction_date
        and claim.instruction_source without error.
        """
        transition_claim_status(self.claim, ClaimStatus.ASSIGNED, self.admin)
        transition_claim_status(self.claim, ClaimStatus.INSPECTION_PENDING, self.surveyor)
        transition_claim_status(self.claim, ClaimStatus.INSPECTION_COMPLETED, self.surveyor)
        transition_claim_status(
            self.claim,
            ClaimStatus.FSR_PREPARED,
            self.surveyor,
            remarks="Direct fast-track FSR with justification"
        )
        self.assertEqual(self.claim.status, ClaimStatus.FSR_PREPARED)
        self.assertFalse(self.claim.ila_reports.exists())

        fsr = FSR.objects.create(
            claim=self.claim,
            report_number='SSLA-91-F-F-269001',
            report_date=date(2026, 9, 22),
            introduction='Fast-tracked FSR introduction...',
            occurrence_details='Occurrence details...',
            survey_details='Survey details...',
            extent_of_loss='Extent of loss...',
            cause_of_loss='Cause of loss...',
            value_at_risk=Decimal('1000000.00'),
            sum_insured=Decimal('1000000.00'),
            underinsurance_percentage=Decimal('0.00'),
            salvage_amount=Decimal('0.00'),
            insured_claim_description='Claimed amount...',
            admissibility='Admissible...',
            final_opinion='Recommended...',
            prepared_by=self.surveyor,
            status=ReportStatus.DRAFT
        )

        pdf_bytes = generate_report_pdf(fsr)
        self.assertTrue(len(pdf_bytes) > 0)

        context = {
            'report': fsr,
            'claim': self.claim,
            'company_email': 'opsmumbai@ssla.global',
            'company_website': 'www.ssla.global',
            'company_address': 'Navi Mumbai',
            'company_name': 'SOTERIA',
            'signatory_name': 'Gautam Acharyya',
            'signatory_designation': 'Principal Surveyor',
            'signatory_license': 'Corporate Survey License No: 200146',
        }
        html = render_to_string('reports/fsr_pdf.html', context)
        self.assertIn('DATE &amp; MODE OF INSTRUCTION', html)
        self.assertIn('10 Sep 2026', html)
        self.assertIn('Official Email Intimation', html)

    def test_fsr_enclosed_documents_includes_submitted_ila_without_manual_verification(self):
        """
        A claim with a generated/submitted ILA PDF (never manually verified) is
        automatically included in the FSR's Document Enclosed list.
        """
        ila = ILA.objects.create(
            claim=self.claim,
            report_number='SSLA-91-F-P-261100',
            report_date=date(2026, 9, 11),
            status=ReportStatus.SUBMITTED,
            prepared_by=self.surveyor,
            instruction_date=date(2026, 9, 10),
            instruction_source='Official Email Intimation',
            surveyor=self.surveyor,
            visit_date=date(2026, 9, 11),
            visit_start_time=time(10, 0),
            visit_end_time=time(12, 0),
            inspection_location='Turbhe, Navi Mumbai',
            person_contacted='Plant Manager',
            contact_number='+91-9876543210',
            policy_number=self.policy.policy_number,
            policy_type=self.policy.policy_type,
            commodity=self.policy.commodity,
            sum_insured=self.policy.sum_insured,
            policy_excess=self.policy.excess,
            survey_and_inspection='Initial inspection completed',
            extent_of_damage='Damage to electrical panel',
            cause_of_damage='Short circuit',
            salvage_prospect='Scrap only',
            estimated_loss=Decimal('350000.00'),
            claimed_amount=Decimal('450000.00'),
            policy_liability='Covered under fire peril',
            budgetary_reserve=Decimal('350000.00')
        )

        # Save ILA PDF as ClaimDocument - system generated
        saved_doc = save_report_pdf_as_document(ila, user=self.surveyor)
        self.assertTrue(saved_doc.verified)

        fsr = FSR.objects.create(
            claim=self.claim,
            report_number='SSLA-91-F-F-261128',
            report_date=date(2026, 9, 22),
            introduction='FSR introduction...',
            occurrence_details='Occurrence details...',
            survey_details='Survey details...',
            extent_of_loss='Extent of loss...',
            cause_of_loss='Cause of loss...',
            value_at_risk=Decimal('5000000.00'),
            sum_insured=Decimal('5000000.00'),
            underinsurance_percentage=Decimal('0.00'),
            salvage_amount=Decimal('0.00'),
            insured_claim_description='Claimed amount...',
            admissibility='Admissible...',
            final_opinion='Final opinion...',
            prepared_by=self.surveyor,
            status=ReportStatus.DRAFT
        )

        # Generate FSR PDF and check enclosed documents
        from reports.services import generate_report_pdf
        pdf_bytes = generate_report_pdf(fsr)
        self.assertTrue(len(pdf_bytes) > 0)

        # Verify through context query that ILA doc is included
        from django.db.models import Q
        enclosed_docs = list(
            self.claim.documents.filter(
                Q(verified=True) | Q(document_type__code__in=['ILA', 'ISR', 'FSR', 'REPORT'])
            ).exclude(
                document_number=fsr.report_number
            )
        )
        self.assertIn(saved_doc, enclosed_docs)
