from datetime import date, time
from decimal import Decimal
from io import BytesIO
from PIL import Image
from django.contrib.admin.sites import AdminSite
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from django.utils import timezone
from surveys.models import (
    SurveyType,
    Inspection,
    InspectionPhoto,
    InspectionObservation,
    FireClaimDetails,
    EngineeringClaimDetails,
    MarineClaimDetails,
    PropertyClaimDetails,
)
from surveys.validators import validate_image_extension, validate_image_size
from claims.models import Insurer, Insured, Policy, Claim, Priority, ClaimStatus
from claims.admin import (
    ClaimAdmin,
    FireClaimDetailsInline,
    EngineeringClaimDetailsInline,
    MarineClaimDetailsInline,
    PropertyClaimDetailsInline,
)

User = get_user_model()


def generate_test_image(filename="test_photo.jpg", image_format="JPEG"):
    """Generate a small valid test image in memory."""
    stream = BytesIO()
    image = Image.new("RGB", (100, 100), color=(0, 128, 255))
    image.save(stream, format=image_format)
    stream.seek(0)
    return SimpleUploadedFile(filename, stream.read(), content_type=f"image/{image_format.lower()}")


class SurveyTypeTests(TestCase):
    def test_seeded_survey_types(self):
        codes = list(SurveyType.objects.values_list('code', flat=True))
        expected_codes = ['ENG', 'FIRE', 'MARINE', 'PROPERTY']
        for expected in expected_codes:
            self.assertIn(expected, codes)

    def test_survey_type_creation(self):
        st = SurveyType.objects.get(code='ENG')
        self.assertEqual(st.name, 'Engineering')
        self.assertTrue(st.is_active)
        self.assertEqual(str(st), 'Engineering (ENG)')


class InspectionModelTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_user(
            username='survey_admin',
            email='admin@survey.test',
            password='password123',
            role=User.Role.ADMIN
        )
        self.surveyor = User.objects.create_user(
            username='field_surveyor',
            email='surveyor@survey.test',
            password='password123',
            role=User.Role.SURVEYOR
        )
        self.survey_type = SurveyType.objects.get(code='FIRE')

        self.insurer = Insurer.objects.create(
            company_name='Reliable Assurance Co',
            branch_name='North Zone Branch',
            address='10 Central Ave',
            city='Metro',
            state='State',
            pincode='100001',
            contact_person='Alice Vance',
            phone='+1-555-0200',
            email='claims@reliable.test'
        )
        self.insured = Insured.objects.create(
            name='Modern Manufacturing Ltd',
            company_name='Modern Group',
            address='Industrial Estate Plot 4',
            city='Metro',
            state='State',
            pincode='100002',
            phone='+1-555-0201',
            email='info@modernmfg.test',
            contact_person='David Miller'
        )
        now = timezone.now()
        self.policy = Policy.objects.create(
            insurer=self.insurer,
            policy_number='POL-FIRE-2026-101',
            policy_type='Standard Fire and Special Perils',
            start_datetime=now,
            end_datetime=now + timezone.timedelta(days=365),
            sum_insured=Decimal('20000000.00'),
            excess=Decimal('50000.00'),
            commodity='Textile Mill Machinery & Fabric Inventory',
            subject_matter='Factory shed, warehouse, spinning machines'
        )
        self.claim = Claim.objects.create(
            survey_type=self.survey_type,
            insurer=self.insurer,
            insured=self.insured,
            policy=self.policy,
            instruction_date=date(2026, 9, 12),
            instruction_source='Direct email intimation',
            date_of_loss=date(2026, 9, 11),
            nature_of_loss='Fire breakout in electrical panel spreading to inventory',
            loss_location='Factory Building 2, Industrial Estate Plot 4',
            claimed_amount=Decimal('3500000.00'),
            priority=Priority.HIGH,
            status=ClaimStatus.NEW,
            created_by=self.admin_user
        )

    def test_multiple_inspections_for_claim(self):
        inspection1 = Inspection.objects.create(
            claim=self.claim,
            surveyor=self.surveyor,
            inspection_date=date(2026, 9, 13),
            start_time=time(10, 0),
            end_time=time(14, 30),
            location='Factory Building 2, Ground Floor',
            person_contacted='David Miller',
            contact_number='+1-555-0201',
            contact_email='david@modernmfg.test',
            site_representative='Plant Operations Head',
            observations='Preliminary visual inspection of scorched wiring and charred fabric rolls.',
            status=Inspection.Status.COMPLETED
        )

        inspection2 = Inspection.objects.create(
            claim=self.claim,
            surveyor=self.surveyor,
            inspection_date=date(2026, 9, 18),
            start_time=time(11, 0),
            end_time=time(13, 0),
            location='Factory Building 2, Salvage Yard',
            person_contacted='David Miller',
            contact_number='+1-555-0201',
            site_representative='Salvage Contractor',
            observations='Follow-up inspection to verify scrap weighment and salvage segregation.',
            status=Inspection.Status.SCHEDULED
        )

        self.assertEqual(self.claim.inspections.count(), 2)
        self.assertIn(inspection1, self.claim.inspections.all())
        self.assertIn(inspection2, self.claim.inspections.all())

    def test_inspection_photo_creation_and_validation(self):
        inspection = Inspection.objects.create(
            claim=self.claim,
            surveyor=self.surveyor,
            inspection_date=date(2026, 9, 13),
            start_time=time(10, 0),
            end_time=time(12, 0),
            location='Factory Building 2',
            person_contacted='David Miller',
            contact_number='+1-555-0201'
        )

        valid_image = generate_test_image("damage_photo.jpg", "JPEG")
        photo = InspectionPhoto.objects.create(
            inspection=inspection,
            image=valid_image,
            caption='Charred electrical distribution board',
            category=InspectionPhoto.Category.DAMAGE,
            latitude=Decimal('18.922000'),
            longitude=Decimal('72.834650'),
            uploaded_by=self.surveyor
        )

        self.assertEqual(photo.category, InspectionPhoto.Category.DAMAGE)
        self.assertEqual(photo.uploaded_by, self.surveyor)
        self.assertIn('damage_photo', photo.image.name)

        invalid_pdf = SimpleUploadedFile("report.pdf", b"%PDF-1.4 dummy data", content_type="application/pdf")
        with self.assertRaises(ValidationError):
            validate_image_extension(invalid_pdf)

        valid_png = generate_test_image("diagram.png", "PNG")
        validate_image_extension(valid_png)

        class OversizedFileMock:
            size = 12 * 1024 * 1024

        with self.assertRaises(ValidationError) as ctx:
            validate_image_size(OversizedFileMock())
        self.assertIn("cannot exceed 10MB", str(ctx.exception))

    def test_inspection_observation_creation(self):
        inspection = Inspection.objects.create(
            claim=self.claim,
            surveyor=self.surveyor,
            inspection_date=date(2026, 9, 13),
            start_time=time(10, 0),
            end_time=time(12, 0),
            location='Factory Building 2',
            person_contacted='David Miller',
            contact_number='+1-555-0201'
        )

        obs = InspectionObservation.objects.create(
            inspection=inspection,
            category='Safety & Fire Protection Equipment',
            description='Fire hydrants had adequate water pressure; smoke detectors operated normally.',
            severity=InspectionObservation.Severity.LOW,
            created_by=self.surveyor
        )

        self.assertEqual(obs.severity, InspectionObservation.Severity.LOW)
        self.assertEqual(obs.created_by, self.surveyor)
        self.assertIn(obs, inspection.observations_list.all())


class SurveyDetailsModelTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_user(
            username='detail_admin',
            email='admin@detail.test',
            password='password123',
            role=User.Role.ADMIN
        )
        self.insurer = Insurer.objects.create(
            company_name='National Alliance Co',
            branch_name='South Branch',
            address='100 Alliance Tower',
            city='Port City',
            state='State',
            pincode='600001',
            contact_person='Frank Taylor',
            phone='+1-555-0400',
            email='taylor@nationalalliance.test'
        )
        self.insured = Insured.objects.create(
            name='Prime Industries Ltd',
            company_name='Prime Group',
            address='SEZ Phase 1',
            city='Port City',
            state='State',
            pincode='600002',
            phone='+1-555-0401',
            email='admin@primeind.test',
            contact_person='Geeta Sharma'
        )
        now = timezone.now()
        self.policy = Policy.objects.create(
            insurer=self.insurer,
            policy_number='POL-COMB-2026-01',
            policy_type='Comprehensive Industrial Risk',
            start_datetime=now,
            end_datetime=now + timezone.timedelta(days=365),
            sum_insured=Decimal('50000000.00'),
            excess=Decimal('100000.00'),
            commodity='Plant & Machinery',
            subject_matter='Factory Complex'
        )

    def _create_claim_with_type(self, type_code):
        st = SurveyType.objects.get(code=type_code)
        return Claim.objects.create(
            survey_type=st,
            insurer=self.insurer,
            insured=self.insured,
            policy=self.policy,
            instruction_date=date(2026, 9, 14),
            instruction_source='Email notification',
            date_of_loss=date(2026, 9, 13),
            nature_of_loss=f'Incident under {type_code}',
            loss_location='SEZ Phase 1 Plot 10',
            created_by=self.admin_user
        )

    def test_fire_claim_details_creation(self):
        claim = self._create_claim_with_type('FIRE')
        fire_details = FireClaimDetails.objects.create(
            claim=claim,
            construction_details='RCC column frame structure with brick infill walls',
            occupancy='Spinning & Weaving Mill',
            building_description='Two-story mill shed measuring approx 12,000 sq ft',
            fire_protection_details='Yard hydrants, smoke detectors, portable fire extinguishers',
            fire_brigade_informed=True,
            fire_brigade_details='MIDC Fire Station dispatched 3 tenders at 02:15 AM',
            police_informed=True,
            police_details='FIR No. 442/2026 registered at Central Station',
            fire_cause='Electrical short circuit in main busbar chamber',
            cause_established=True,
            point_of_origin='Ground floor electrical control room'
        )

        self.assertEqual(claim.fire_details, fire_details)
        self.assertTrue(fire_details.cause_established)
        self.assertIn('Fire Details for Claim', str(fire_details))

    def test_engineering_claim_details_creation(self):
        claim = self._create_claim_with_type('ENG')
        eng_details = EngineeringClaimDetails.objects.create(
            claim=claim,
            equipment_name='1000 kVA Step-Down Transformer',
            manufacturer='ABB Power Grids',
            model='TX-1000-KVA',
            serial_number='ABB-2021-99881',
            year_of_manufacture=2021,
            installation_date=date(2021, 6, 15),
            machine_location='Substation Yard #2',
            breakdown_description='Sudden tripping of primary breaker with oil discharge',
            damage_description='HV winding flashover, severe deformation of core laminations',
            cause_of_breakdown='Internal insulation degradation due to voltage surge',
            repair_estimate=Decimal('1250000.00'),
            replacement_cost=Decimal('2800000.00'),
            parts_cost=Decimal('850000.00'),
            labour_cost=Decimal('250000.00'),
            testing_cost=Decimal('150000.00'),
            salvage='Copper scrap and transformer tank oil'
        )

        self.assertEqual(claim.engineering_details, eng_details)
        self.assertEqual(eng_details.repair_estimate, Decimal('1250000.00'))
        self.assertIn('ABB-2021-99881', eng_details.serial_number)

    def test_marine_claim_details_creation(self):
        claim = self._create_claim_with_type('MARINE')
        marine_details = MarineClaimDetails.objects.create(
            claim=claim,
            vessel_name='MV Ocean Pioneer',
            voyage_number='V-2026-44',
            port_of_loading='Port of Singapore',
            port_of_discharge='Nhava Sheva Port, India',
            place_of_survey='CFS Yard Bay 6, Dronagiri',
            cargo_description='Precision CNC Lathe Machines in wooden crates',
            consignor='Singa Machinery PTE',
            consignee='Prime Industries Ltd',
            bill_of_lading_number='BL-SIN-NSA-99231',
            container_number='MSCU-883491-0',
            package_count=4,
            damage_description='Seawater ingress resulting in extensive rust and electrical oxidation',
            transit_details='Vessel encountered typhoon conditions in Bay of Bengal',
            packing_condition='Vacuum sealed foil within treated timber cases; foil breached',
            salvage_details='Machines to be salvaged for non-electrical steel parts'
        )

        self.assertEqual(claim.marine_details, marine_details)
        self.assertEqual(marine_details.port_of_loading, 'Port of Singapore')
        self.assertIn('MV Ocean Pioneer', str(marine_details))

    def test_property_claim_details_creation(self):
        claim = self._create_claim_with_type('PROPERTY')
        prop_details = PropertyClaimDetails.objects.create(
            claim=claim,
            property_type='Commercial Office Building',
            occupancy='Corporate Administrative Headquarters',
            construction_type='First Class RCC & Glass Curtain Wall',
            building_area=Decimal('25000.00'),
            number_of_floors=5,
            building_description='Modern corporate office tower with basement parking',
            contents_description='Workstations, servers, conference AV systems, executive furniture',
            damage_description='Heavy water logging on ground and basement floors following flash flood',
            repair_estimate=Decimal('4200000.00'),
            replacement_cost=Decimal('8500000.00'),
            salvage='Damaged furniture and server rack frames'
        )

        self.assertEqual(claim.property_details, prop_details)
        self.assertEqual(prop_details.number_of_floors, 5)
        self.assertIn('Commercial Office Building', str(prop_details))

    def test_claim_admin_dynamic_inlines(self):
        site = AdminSite()
        claim_admin = ClaimAdmin(Claim, site)
        factory = RequestFactory()
        request = factory.get('/admin/claims/claim/')

        fire_claim = self._create_claim_with_type('FIRE')
        inlines_fire = claim_admin.get_inlines(request, fire_claim)
        self.assertIn(FireClaimDetailsInline, inlines_fire)
        self.assertNotIn(EngineeringClaimDetailsInline, inlines_fire)

        eng_claim = self._create_claim_with_type('ENG')
        inlines_eng = claim_admin.get_inlines(request, eng_claim)
        self.assertIn(EngineeringClaimDetailsInline, inlines_eng)
        self.assertNotIn(FireClaimDetailsInline, inlines_eng)

        marine_claim = self._create_claim_with_type('MARINE')
        inlines_marine = claim_admin.get_inlines(request, marine_claim)
        self.assertIn(MarineClaimDetailsInline, inlines_marine)

        prop_claim = self._create_claim_with_type('PROPERTY')
        inlines_prop = claim_admin.get_inlines(request, prop_claim)
        self.assertIn(PropertyClaimDetailsInline, inlines_prop)
