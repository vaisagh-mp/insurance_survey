from datetime import date, time
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from surveys.models import SurveyType
from claims.models import Insurer, Insured, Policy, Claim, Priority, ClaimStatus
from assessments.models import Assessment, AssessmentItem
from assessments.services import recalculate_assessment
from reports.models import AuditLog, ILA, ISR, FSR, ReportStatus
from reports.services import log_action

User = get_user_model()


class ReportModelTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_user(
            username='report_admin',
            email='admin@report.test',
            password='password123',
            role=User.Role.ADMIN
        )
        self.surveyor = User.objects.create_user(
            username='report_surveyor',
            email='surveyor@report.test',
            password='password123',
            role=User.Role.SURVEYOR
        )
        self.survey_type = SurveyType.objects.get(code='FIRE')

        self.insurer = Insurer.objects.create(
            company_name='National Fire & Marine Co',
            branch_name='Central Operations',
            address='88 Mercantile Chambers',
            city='Metro City',
            state='State',
            pincode='800001',
            contact_person='Patricia Hall',
            phone='+1-555-0600',
            email='claims@nationalfire.test'
        )
        self.insured = Insured.objects.create(
            name='Evergreen Warehousing Corp',
            company_name='Evergreen Logistics Ltd',
            address='Logistics Park Block B',
            city='Metro City',
            state='State',
            pincode='800002',
            phone='+1-555-0601',
            email='ops@evergreenlog.test',
            contact_person='Vikram Sen'
        )
        now = timezone.now()
        self.policy = Policy.objects.create(
            insurer=self.insurer,
            policy_number='POL-FIR-2026-0044',
            policy_type='Standard Fire & Allied Perils',
            start_datetime=now,
            end_datetime=now + timezone.timedelta(days=365),
            sum_insured=Decimal('30000000.00'),
            excess=Decimal('25000.00'),
            commodity='Stored Commodities & FMCG Goods',
            subject_matter='Warehouse Building B2'
        )
        self.claim = Claim.objects.create(
            survey_type=self.survey_type,
            insurer=self.insurer,
            insured=self.insured,
            policy=self.policy,
            instruction_date=date(2026, 9, 10),
            instruction_source='Official Email Intimation',
            date_of_loss=date(2026, 9, 9),
            nature_of_loss='Fire breakout due to electrical short circuit',
            loss_location='Warehouse Building B2, Bay 1-4',
            claimed_amount=Decimal('4500000.00'),
            priority=Priority.HIGH,
            status=ClaimStatus.INSPECTION_COMPLETED,
            created_by=self.admin_user
        )

    def test_audit_log_creation_and_helper(self):
        log = log_action(
            user=self.admin_user,
            action="TEST_REPORT_ACTION",
            obj=self.claim,
            description="Testing report action logging"
        )
        self.assertEqual(log.user, self.admin_user)
        self.assertEqual(log.action, "TEST_REPORT_ACTION")
        self.assertEqual(log.model_name, "Claim")
        self.assertEqual(log.object_id, str(self.claim.pk))

    def test_ila_creation(self):
        ila = ILA.objects.create(
            claim=self.claim,
            report_number='ILA-2026-001',
            report_date=date(2026, 9, 11),
            status=ReportStatus.DRAFT,
            version_number=1,
            prepared_by=self.surveyor,
            instruction_date=date(2026, 9, 10),
            instruction_source='Official Email Intimation',
            surveyor=self.surveyor,
            visit_date=date(2026, 9, 11),
            visit_start_time=time(10, 0),
            visit_end_time=time(15, 0),
            inspection_location='Warehouse Building B2, Bay 1-4',
            person_contacted='Vikram Sen',
            contact_number='+1-555-0601',
            contact_email='ops@evergreenlog.test',
            policy_number='POL-FIR-2026-0044',
            policy_type='Standard Fire & Allied Perils',
            commodity='Stored Commodities & FMCG Goods',
            sum_insured=Decimal('30000000.00'),
            policy_excess=Decimal('25000.00'),
            survey_and_inspection='Inspected damaged inventory stacks, charred roof trusses, and soot deposits',
            extent_of_damage='Bays 1 and 2 severely damaged, Bays 3 and 4 water-damaged during firefighting',
            cause_of_damage='Electrical short circuit in main distribution panel',
            salvage_prospect='Canned food items in Bay 4 can be segregated and salvaged',
            estimated_loss=Decimal('3800000.00'),
            claimed_amount=Decimal('4500000.00'),
            policy_liability='Loss falls within policy perils under Clause 1 (Fire)',
            budgetary_reserve=Decimal('3500000.00'),
            remarks='Advised insured to segregate sound stock from affected inventory'
        )

        self.assertEqual(ila.report_number, 'ILA-2026-001')
        self.assertEqual(ila.status, ReportStatus.DRAFT)
        self.assertEqual(ila.surveyor, self.surveyor)
        self.assertIn(ila, self.claim.ila_reports.all())

    def test_isr_creation(self):
        isr = ISR.objects.create(
            claim=self.claim,
            report_number='ISR-2026-001',
            report_date=date(2026, 9, 18),
            status=ReportStatus.SUBMITTED,
            version_number=1,
            prepared_by=self.surveyor,
            submitted_at=timezone.now(),
            introduction='Interim Survey Report on commercial fire loss at Evergreen Warehousing Corp',
            occurrence_details='Fire broke out on 2026-09-09 at 22:30 hrs; extinguished by fire brigade at 04:00 hrs',
            survey_details='Detailed joint inspection conducted with insured representatives and loss adjusters',
            extent_of_damage='Severe structural damage to roof trusses; 40% inventory total loss, 25% salvageable',
            cause_of_loss='Accidental electrical ignition in electrical riser',
            initial_assessment='Preliminary loss assessed in the range of 3.2 to 3.6 Million Rupees',
            policy_liability='Liability confirmed in principle subject to receipt of fire brigade report and forensic NOC',
            documents_received='Policy copy, Claim form, Fire brigade receipt intimation',
            documents_pending='Final Police Panchanama, Fire Brigade incident report, Itemized stock ledger',
            remarks='Immediate provisional on-account payment recommended',
            recommendation='Release on-account payment of Rs. 1,000,000 subject to underwriter approval'
        )

        self.assertEqual(isr.report_number, 'ISR-2026-001')
        self.assertEqual(isr.status, ReportStatus.SUBMITTED)
        self.assertIn(isr, self.claim.isr_reports.all())

    def test_fsr_creation_and_assessment_link(self):
        # Create an Assessment with items
        assessment = Assessment.objects.create(
            claim=self.claim,
            underinsurance_percentage=Decimal('10.00'),
            salvage_amount=Decimal('50000.00'),
            depreciation_amount=Decimal('100000.00'),
            policy_excess=Decimal('25000.00'),
            created_by=self.admin_user
        )
        AssessmentItem.objects.create(
            assessment=assessment,
            description='Warehouse building reconstruction and structural steel trusses',
            quantity=Decimal('1.00'),
            rate=Decimal('2000000.00'),
            claimed_amount=Decimal('2500000.00')
        )
        recalculate_assessment(assessment)
        assessment.refresh_from_db()

        # Gross: 2,000,000. Underinsurance: 200,000. Adjusted: 2,000,000 - 50,000 - 200,000 - 100,000 = 1,650,000.
        # Net: 1,650,000 - 25,000 = 1,625,000.
        self.assertEqual(assessment.gross_assessed_loss, Decimal('2000000.00'))
        self.assertEqual(assessment.net_assessed_loss, Decimal('1625000.00'))

        # Create FSR linking to this Assessment
        fsr = FSR.objects.create(
            claim=self.claim,
            report_number='FSR-2026-001',
            report_date=date(2026, 9, 30),
            status=ReportStatus.FINAL,
            version_number=1,
            prepared_by=self.surveyor,
            submitted_at=timezone.now(),
            approved_at=timezone.now(),
            introduction='Final Survey Report for commercial fire claim',
            occurrence_details='Fire occurrence confirmed by MIDC Fire Station report',
            survey_details='Comprehensive inspection, verification of accounts and scrap salvage tenders',
            extent_of_loss='Total physical damage to Bay 1-2 building structure and stored materials',
            cause_of_loss='Electrical arcing confirmed as accidental origin',
            value_at_risk=Decimal('33000000.00'),
            sum_insured=Decimal('30000000.00'),
            underinsurance_percentage=Decimal('10.00'),
            salvage_description='Scrap metal sold through public competitive bidding',
            salvage_amount=Decimal('50000.00'),
            insured_claim_description='Claim submitted for rebuilding and stock losses amounting to Rs. 4,500,000',
            admissibility='Loss is fully admissible within policy coverage terms',
            policy_coverage='Coverage under Standard Fire & Special Perils Material Damage Section',
            policy_exclusions='No policy exclusion clauses applicable to this occurrence',
            breach_of_warranty=False,
            warranty_details='All electrical safety and fire protection warranties duly complied with',
            remarks='Survey completed in full cooperation with insured and insurer officials',
            final_opinion='Recommended net settlement of Rs. 1,625,000 in full and final settlement',
            assessment=assessment
        )

        # Verify FSR reads financial figures from Assessment without re-typing
        self.assertEqual(fsr.assessment, assessment)
        self.assertEqual(fsr.gross_assessed_loss, Decimal('2000000.00'))
        self.assertEqual(fsr.net_assessed_loss, Decimal('1625000.00'))

        # Verify constant disclaimer note
        expected_note = "Subject to the terms and conditions of the insurance policy and final insurer decision"
        self.assertEqual(FSR.DISCLAIMER_NOTE, expected_note)
        self.assertIn("Subject to the terms and conditions", FSR.DISCLAIMER_NOTE)


from rest_framework.test import APITestCase
from rest_framework import status
from surveys.models import FireClaimDetails
from claims.models import SurveyAssignment
from documents.models import ClaimDocument, DocumentType
from reports.services import generate_report_pdf, save_report_pdf_as_document


class ReportPDFTests(APITestCase):
    def setUp(self):
        self.admin_user = User.objects.create_user(
            username='pdf_admin',
            email='admin@pdf.test',
            password='password123',
            role=User.Role.ADMIN
        )
        self.surveyor_a = User.objects.create_user(
            username='assigned_surveyor',
            email='surveyor_a@pdf.test',
            password='password123',
            role=User.Role.SURVEYOR
        )
        self.surveyor_b = User.objects.create_user(
            username='unassigned_surveyor',
            email='surveyor_b@pdf.test',
            password='password123',
            role=User.Role.SURVEYOR
        )

        self.survey_type = SurveyType.objects.get(code='FIRE')
        self.insurer = Insurer.objects.create(
            company_name='Atlas Insurance Co',
            branch_name='North Zone',
            address='123 Commercial Way',
            city='Metro',
            state='State',
            pincode='110001',
            contact_person='Alan Smith',
            phone='+1-555-9876',
            email='claims@atlas.test'
        )
        self.insured = Insured.objects.create(
            name='Apex Logistics Pvt Ltd',
            company_name='Apex Corp',
            address='45 Industrial Area',
            city='Metro',
            state='State',
            pincode='110002',
            phone='+1-555-1234',
            email='ops@apex.test',
            contact_person='Rajiv Sharma'
        )
        now = timezone.now()
        self.policy = Policy.objects.create(
            insurer=self.insurer,
            policy_number='POL-PDF-2026-001',
            policy_type='Standard Fire & Special Perils',
            start_datetime=now,
            end_datetime=now + timezone.timedelta(days=365),
            sum_insured=Decimal('15000000.00'),
            excess=Decimal('50000.00'),
            commodity='Electronic Goods & Spares',
            subject_matter='Warehouse Unit 3'
        )
        self.claim = Claim.objects.create(
            survey_type=self.survey_type,
            insurer=self.insurer,
            insured=self.insured,
            policy=self.policy,
            instruction_date=date(2026, 9, 10),
            instruction_source='Direct Email',
            date_of_loss=date(2026, 9, 9),
            nature_of_loss='Fire incident',
            loss_location='Warehouse Unit 3, Industrial Area',
            claimed_amount=Decimal('3000000.00'),
            priority=Priority.HIGH,
            status=ClaimStatus.ASSIGNED,
            created_by=self.admin_user
        )

        # Assign surveyor_a
        self.assignment = SurveyAssignment.objects.create(
            claim=self.claim,
            surveyor=self.surveyor_a,
            assigned_by=self.admin_user,
            due_date=date(2026, 9, 25),
            status=SurveyAssignment.Status.ASSIGNED
        )

        # Survey type specific details
        self.fire_details = FireClaimDetails.objects.create(
            claim=self.claim,
            construction_details='Class A Concrete Frame with insulated sheet roofing',
            occupancy='Commercial Electronic Warehousing',
            building_description='Two-storey standalone RCC warehouse building',
            fire_protection_details='Hydrant ring main and portable CO2 fire extinguishers',
            fire_brigade_informed=True,
            fire_brigade_details='MIDC Fire Station Engine #4 attended within 20 mins',
            police_informed=True,
            police_details='FIR recorded at Metro Central Police Station',
            fire_cause='Electrical short-circuit near charger bank',
            cause_established=True,
            point_of_origin='Ground Floor Battery Charging Racks',
            storage_details='Palletized racks with 3-tier storage',
            machinery_details='Forklifts and automated conveyors',
            stock_details='Circuit boards, controllers, power packs',
            salvage_observation='Sealed metal casing equipment salvageable'
        )

        # Assessment and items
        self.assessment = Assessment.objects.create(
            claim=self.claim,
            underinsurance_percentage=Decimal('5.00'),
            salvage_amount=Decimal('100000.00'),
            depreciation_amount=Decimal('50000.00'),
            policy_excess=Decimal('50000.00'),
            assessment_remarks='Assessed based on manufacturer replacement price lists.',
            created_by=self.admin_user
        )
        AssessmentItem.objects.create(
            assessment=self.assessment,
            item_code='ELEC-001',
            description='Power Distribution Unit 400A',
            specification='Three-phase switchgear',
            quantity=Decimal('2.00'),
            rate=Decimal('250000.00'),
            claimed_amount=Decimal('600000.00')
        )
        AssessmentItem.objects.create(
            assessment=self.assessment,
            item_code='ELEC-002',
            description='Sub-assembly circuit controllers',
            specification='OEM batch controllers',
            quantity=Decimal('100.00'),
            rate=Decimal('15000.00'),
            claimed_amount=Decimal('1800000.00')
        )
        recalculate_assessment(self.assessment)
        self.assessment.refresh_from_db()

        # Create ILA, ISR, and FSR records
        self.ila = ILA.objects.create(
            claim=self.claim,
            report_number='ILA-TEST-001',
            report_date=date(2026, 9, 11),
            status=ReportStatus.DRAFT,
            version_number=1,
            prepared_by=self.surveyor_a,
            instruction_date=date(2026, 9, 10),
            instruction_source='Insurer Email',
            surveyor=self.surveyor_a,
            visit_date=date(2026, 9, 11),
            visit_start_time=time(9, 30),
            visit_end_time=time(14, 0),
            inspection_location='Warehouse Unit 3',
            person_contacted='Rajiv Sharma',
            contact_number='+1-555-1234',
            contact_email='ops@apex.test',
            policy_number='POL-PDF-2026-001',
            policy_type='Fire & Special Perils',
            commodity='Electronic Goods',
            sum_insured=Decimal('15000000.00'),
            policy_excess=Decimal('50000.00'),
            survey_and_inspection='Initial physical inspection completed',
            extent_of_damage='Heavy smoke damage to floor 1, structural burn on east wall',
            cause_of_damage='Electrical short circuit',
            salvage_prospect='Moderate salvage expected from sealed goods',
            estimated_loss=Decimal('2200000.00'),
            claimed_amount=Decimal('3000000.00'),
            policy_liability='Prima facie admissible under Section 1',
            budgetary_reserve=Decimal('2000000.00')
        )

        self.isr = ISR.objects.create(
            claim=self.claim,
            report_number='ISR-TEST-001',
            report_date=date(2026, 9, 15),
            status=ReportStatus.SUBMITTED,
            version_number=1,
            prepared_by=self.surveyor_a,
            introduction='Interim survey report on electronic goods fire incident',
            occurrence_details='Fire broke out in warehouse unit on Sep 9 night',
            survey_details='Joint survey conducted with warehouse in-charge',
            extent_of_damage='200 units damaged by water and heat',
            cause_of_loss='Electrical overheating',
            initial_assessment='Loss expected around Rs 2,000,000',
            policy_liability='Admissible subject to forensic electrical report',
            documents_received='Claim Form, Initial Estimates',
            documents_pending='Fire Brigade Report, Original Purchase Registers',
            recommendation='Ad-hoc advance of Rs 500,000 recommended'
        )

        self.fsr = FSR.objects.create(
            claim=self.claim,
            report_number='FSR-TEST-001',
            report_date=date(2026, 9, 25),
            status=ReportStatus.FINAL,
            version_number=1,
            prepared_by=self.surveyor_a,
            introduction='Final Survey Report for electronic warehouse fire loss',
            occurrence_details='Occurrence verified with fire department records',
            survey_details='Final inventory audit and salvage negotiation completed',
            extent_of_loss='102 major electrical units destroyed, remainder salvaged',
            cause_of_loss='Electrical arcing at main busbar',
            value_at_risk=Decimal('16000000.00'),
            sum_insured=Decimal('15000000.00'),
            underinsurance_percentage=Decimal('5.00'),
            salvage_description='Bidded scrap lot sold to licensed recycler',
            salvage_amount=Decimal('100000.00'),
            insured_claim_description='Original claim Rs 3,000,000 for all damaged stock',
            admissibility='Fully admissible under policy perils',
            policy_coverage='Standard Fire Policy Material Damage',
            policy_exclusions='None applicable',
            breach_of_warranty=False,
            warranty_details='All conditions satisfied',
            remarks='Claim processed in agreed timelines',
            final_opinion='Recommended settlement of net loss.',
            assessment=self.assessment
        )

    def test_generate_report_pdf_bytes(self):
        """Verify generate_report_pdf creates non-empty PDF bytes starting with %PDF-."""
        ila_pdf = generate_report_pdf(self.ila)
        self.assertIsInstance(ila_pdf, bytes)
        self.assertTrue(ila_pdf.startswith(b'%PDF-'))
        self.assertGreater(len(ila_pdf), 1000)

        isr_pdf = generate_report_pdf(self.isr)
        self.assertIsInstance(isr_pdf, bytes)
        self.assertTrue(isr_pdf.startswith(b'%PDF-'))
        self.assertGreater(len(isr_pdf), 1000)

        fsr_pdf = generate_report_pdf(self.fsr)
        self.assertIsInstance(fsr_pdf, bytes)
        self.assertTrue(fsr_pdf.startswith(b'%PDF-'))
        self.assertGreater(len(fsr_pdf), 1000)

    def test_save_report_pdf_as_document_and_idempotence(self):
        """Verify save_report_pdf_as_document generates and stores ClaimDocument with history preservation."""
        doc1 = save_report_pdf_as_document(self.ila, self.surveyor_a)
        self.assertIsInstance(doc1, ClaimDocument)
        self.assertEqual(doc1.claim, self.claim)
        self.assertEqual(doc1.document_type.code, 'ILA')
        self.assertEqual(doc1.document_number, self.ila.report_number)
        self.assertEqual(doc1.uploaded_by, self.surveyor_a)
        self.assertTrue(doc1.file.name.endswith('.pdf'))

        # Generating again creates a fresh new row without deleting/overwriting doc1
        doc2 = save_report_pdf_as_document(self.ila, self.surveyor_a)
        self.assertNotEqual(doc1.pk, doc2.pk)
        self.assertEqual(ClaimDocument.objects.filter(claim=self.claim, document_type__code='ILA').count(), 2)

    def test_preview_pdf_endpoints(self):
        """Verify preview-pdf streams PDF inline with proper headers."""
        self.client.force_authenticate(user=self.surveyor_a)

        # ILA preview
        res_ila = self.client.get(f'/api/ila/{self.ila.id}/preview-pdf/')
        self.assertEqual(res_ila.status_code, status.HTTP_200_OK)
        self.assertEqual(res_ila['Content-Type'], 'application/pdf')
        self.assertIn(f'inline; filename="{self.ila.report_number}.pdf"', res_ila['Content-Disposition'])
        self.assertTrue(res_ila.content.startswith(b'%PDF-'))

        # ISR preview
        res_isr = self.client.get(f'/api/isr/{self.isr.id}/preview-pdf/')
        self.assertEqual(res_isr.status_code, status.HTTP_200_OK)
        self.assertEqual(res_isr['Content-Type'], 'application/pdf')
        self.assertIn(f'inline; filename="{self.isr.report_number}.pdf"', res_isr['Content-Disposition'])

        # FSR preview
        res_fsr = self.client.get(f'/api/fsr/{self.fsr.id}/preview-pdf/')
        self.assertEqual(res_fsr.status_code, status.HTTP_200_OK)
        self.assertEqual(res_fsr['Content-Type'], 'application/pdf')
        self.assertIn(f'inline; filename="{self.fsr.report_number}.pdf"', res_fsr['Content-Disposition'])

    def test_generate_pdf_endpoints(self):
        """Verify generate-pdf endpoint creates and returns ClaimDocument."""
        self.client.force_authenticate(user=self.surveyor_a)

        # POST generate-pdf for FSR
        res = self.client.post(f'/api/fsr/{self.fsr.id}/generate-pdf/')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data['document_number'], self.fsr.report_number)
        self.assertEqual(res.data['claim'], self.claim.id)
        self.assertIn('.pdf', res.data['file'])

        # Check DB
        claim_doc = ClaimDocument.objects.get(id=res.data['id'])
        self.assertEqual(claim_doc.document_type.code, 'FSR')
        self.assertEqual(claim_doc.uploaded_by, self.surveyor_a)

    def test_permission_enforcement_on_pdf_actions(self):
        """Unassigned surveyor cannot preview or generate PDF; assigned surveyor and admin can."""
        # Unassigned surveyor attempts access
        self.client.force_authenticate(user=self.surveyor_b)
        res_preview = self.client.get(f'/api/ila/{self.ila.id}/preview-pdf/')
        self.assertIn(res_preview.status_code, [status.HTTP_404_NOT_FOUND, status.HTTP_403_FORBIDDEN])

        res_generate = self.client.post(f'/api/ila/{self.ila.id}/generate-pdf/')
        self.assertIn(res_generate.status_code, [status.HTTP_404_NOT_FOUND, status.HTTP_403_FORBIDDEN])

        # Admin user can access
        self.client.force_authenticate(user=self.admin_user)
        res_admin_prev = self.client.get(f'/api/ila/{self.ila.id}/preview-pdf/')
        self.assertEqual(res_admin_prev.status_code, status.HTTP_200_OK)

        res_admin_gen = self.client.post(f'/api/ila/{self.ila.id}/generate-pdf/')
        self.assertEqual(res_admin_gen.status_code, status.HTTP_201_CREATED)

