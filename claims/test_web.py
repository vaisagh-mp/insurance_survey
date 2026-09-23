from datetime import date
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.utils import timezone

from claims.models import Claim, ClaimStatus, Insurer, Insured, Policy, SurveyAssignment, Priority
from surveys.models import SurveyType
from accounts.models import SurveyorProfile

User = get_user_model()


class AdminWebPortalTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin_user = User.objects.create_user(
            username='admin_web',
            email='admin@portal.test',
            password='password123',
            role=User.Role.ADMIN
        )
        self.surveyor_user = User.objects.create_user(
            username='surveyor_web',
            email='surveyor@portal.test',
            password='password123',
            role=User.Role.SURVEYOR
        )
        SurveyorProfile.objects.create(
            user=self.surveyor_user,
            license_number='LIC-WEB-001',
            license_expiry=date(2028, 1, 1),
            phone='555-0101',
            specialization='Fire & Engineering'
        )

        self.survey_type = SurveyType.objects.get(code='FIRE')
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
            policy_number='POL-WEB-2026-0001',
            policy_type='Fire Policy',
            start_datetime=now,
            end_datetime=now + timezone.timedelta(days=365),
            sum_insured=Decimal('10000000.00'),
            excess=Decimal('25000.00'),
            commodity='Plant & Machinery',
            subject_matter='Factory Building'
        )

    def test_permission_gates_and_login_redirect(self):
        """Anonymous redirected to login; surveyor gets 403; admin gets 200."""
        # Anonymous
        resp = self.client.get('/dashboard/admin/')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login/', resp.url)

        # Surveyor (non-admin)
        self.client.force_login(self.surveyor_user)
        resp = self.client.get('/dashboard/admin/')
        self.assertEqual(resp.status_code, 403)

        # Admin
        self.client.force_login(self.admin_user)
        resp = self.client.get('/dashboard/admin/')
        self.assertEqual(resp.status_code, 200)

    def test_dashboard_stat_tiles_exact_mapping(self):
        """Verify the exact status mapping required for all 12 tiles."""
        self.client.force_login(self.admin_user)

        # 1. New claim (no assignments -> also unassigned)
        c_new = Claim.objects.create(
            survey_type=self.survey_type, insurer=self.insurer, insured=self.insured, policy=self.policy,
            instruction_date=date(2026, 9, 1), instruction_source='Email', date_of_loss=date(2026, 8, 30),
            nature_of_loss='Fire', loss_location='Site A', claimed_amount=Decimal('50000.00'),
            status=ClaimStatus.NEW, created_by=self.admin_user
        )

        # 2. Assigned claim (has active assignment -> NOT unassigned)
        c_assigned = Claim.objects.create(
            survey_type=self.survey_type, insurer=self.insurer, insured=self.insured, policy=self.policy,
            instruction_date=date(2026, 9, 2), instruction_source='Email', date_of_loss=date(2026, 8, 30),
            nature_of_loss='Fire', loss_location='Site B', claimed_amount=Decimal('60000.00'),
            status=ClaimStatus.ASSIGNED, created_by=self.admin_user
        )
        SurveyAssignment.objects.create(
            claim=c_assigned, surveyor=self.surveyor_user, assigned_by=self.admin_user,
            due_date=date(2026, 9, 20), status=SurveyAssignment.Status.ASSIGNED
        )

        # 3. Unassigned claim that has only REASSIGNED assignments (status=INSPECTION_PENDING)
        c_reassigned = Claim.objects.create(
            survey_type=self.survey_type, insurer=self.insurer, insured=self.insured, policy=self.policy,
            instruction_date=date(2026, 9, 3), instruction_source='Email', date_of_loss=date(2026, 8, 30),
            nature_of_loss='Fire', loss_location='Site C', claimed_amount=Decimal('70000.00'),
            status=ClaimStatus.INSPECTION_PENDING, created_by=self.admin_user
        )
        SurveyAssignment.objects.create(
            claim=c_reassigned, surveyor=self.surveyor_user, assigned_by=self.admin_user,
            due_date=date(2026, 9, 20), status=SurveyAssignment.Status.REASSIGNED
        )

        # 4. Inspection Completed -> ILA Pending
        Claim.objects.create(
            survey_type=self.survey_type, insurer=self.insurer, insured=self.insured, policy=self.policy,
            instruction_date=date(2026, 9, 4), instruction_source='Email', date_of_loss=date(2026, 8, 30),
            nature_of_loss='Fire', loss_location='Site D', claimed_amount=Decimal('80000.00'),
            status=ClaimStatus.INSPECTION_COMPLETED, created_by=self.admin_user
        )

        # 5. ILA Prepared -> LOR Pending
        Claim.objects.create(
            survey_type=self.survey_type, insurer=self.insurer, insured=self.insured, policy=self.policy,
            instruction_date=date(2026, 9, 5), instruction_source='Email', date_of_loss=date(2026, 8, 30),
            nature_of_loss='Fire', loss_location='Site E', claimed_amount=Decimal('90000.00'),
            status=ClaimStatus.ILA_PREPARED, created_by=self.admin_user
        )

        # 6. LOR Issued & Document Collection -> Assessment Pending (2 claims)
        Claim.objects.create(
            survey_type=self.survey_type, insurer=self.insurer, insured=self.insured, policy=self.policy,
            instruction_date=date(2026, 9, 6), instruction_source='Email', date_of_loss=date(2026, 8, 30),
            nature_of_loss='Fire', loss_location='Site F', claimed_amount=Decimal('100000.00'),
            status=ClaimStatus.LOR_ISSUED, created_by=self.admin_user
        )
        Claim.objects.create(
            survey_type=self.survey_type, insurer=self.insurer, insured=self.insured, policy=self.policy,
            instruction_date=date(2026, 9, 7), instruction_source='Email', date_of_loss=date(2026, 8, 30),
            nature_of_loss='Fire', loss_location='Site G', claimed_amount=Decimal('110000.00'),
            status=ClaimStatus.DOCUMENT_COLLECTION, created_by=self.admin_user
        )

        # 7. Assessment in progress -> ISR Pending
        Claim.objects.create(
            survey_type=self.survey_type, insurer=self.insurer, insured=self.insured, policy=self.policy,
            instruction_date=date(2026, 9, 8), instruction_source='Email', date_of_loss=date(2026, 8, 30),
            nature_of_loss='Fire', loss_location='Site H', claimed_amount=Decimal('120000.00'),
            status=ClaimStatus.ASSESSMENT_IN_PROGRESS, created_by=self.admin_user
        )

        # 8. ISR Prepared -> FSR Pending
        Claim.objects.create(
            survey_type=self.survey_type, insurer=self.insurer, insured=self.insured, policy=self.policy,
            instruction_date=date(2026, 9, 9), instruction_source='Email', date_of_loss=date(2026, 8, 30),
            nature_of_loss='Fire', loss_location='Site I', claimed_amount=Decimal('130000.00'),
            status=ClaimStatus.ISR_PREPARED, created_by=self.admin_user
        )

        # 9. Report Submitted
        Claim.objects.create(
            survey_type=self.survey_type, insurer=self.insurer, insured=self.insured, policy=self.policy,
            instruction_date=date(2026, 9, 10), instruction_source='Email', date_of_loss=date(2026, 8, 30),
            nature_of_loss='Fire', loss_location='Site J', claimed_amount=Decimal('140000.00'),
            status=ClaimStatus.REPORT_SUBMITTED, created_by=self.admin_user
        )

        # 10. Closed
        Claim.objects.create(
            survey_type=self.survey_type, insurer=self.insurer, insured=self.insured, policy=self.policy,
            instruction_date=date(2026, 9, 11), instruction_source='Email', date_of_loss=date(2026, 8, 30),
            nature_of_loss='Fire', loss_location='Site K', claimed_amount=Decimal('150000.00'),
            status=ClaimStatus.CLOSED, created_by=self.admin_user
        )

        resp = self.client.get('/dashboard/admin/')
        self.assertEqual(resp.status_code, 200)

        tiles_dict = {t['title']: t['count'] for t in resp.context['tiles']}

        self.assertEqual(tiles_dict['Total Claims'], 11)
        self.assertEqual(tiles_dict['New'], 1)
        # Unassigned: c_new (0 assignments) and c_reassigned (only REASSIGNED assignments) + 8 others without assignments = 10
        # Only c_assigned has active assignment!
        self.assertEqual(tiles_dict['Unassigned'], 10)
        self.assertEqual(tiles_dict['Assigned'], 1)
        self.assertEqual(tiles_dict['Inspection Pending'], 1)
        self.assertEqual(tiles_dict['ILA Pending'], 1)
        self.assertEqual(tiles_dict['LOR Pending'], 1)
        self.assertEqual(tiles_dict['Assessment Pending'], 2)
        self.assertEqual(tiles_dict['ISR Pending'], 1)
        self.assertEqual(tiles_dict['FSR Pending'], 1)
        self.assertEqual(tiles_dict['Submitted'], 1)
        self.assertEqual(tiles_dict['Closed'], 1)

        # Verify recent claims in context
        self.assertIn('recent_claims', resp.context)
        self.assertLessEqual(len(resp.context['recent_claims']), 10)

    def test_claims_list_filtering_and_in_progress(self):
        """Test claims filtering including the custom in_progress definition."""
        self.client.force_login(self.admin_user)

        # Create claims with different statuses
        c1 = Claim.objects.create(
            survey_type=self.survey_type, insurer=self.insurer, insured=self.insured, policy=self.policy,
            instruction_date=date(2026, 9, 1), instruction_source='Email', date_of_loss=date(2026, 8, 30),
            nature_of_loss='Fire', loss_location='Site 1', claimed_amount=Decimal('10000.00'),
            status=ClaimStatus.NEW, created_by=self.admin_user
        )
        c2 = Claim.objects.create(
            survey_type=self.survey_type, insurer=self.insurer, insured=self.insured, policy=self.policy,
            instruction_date=date(2026, 9, 2), instruction_source='Email', date_of_loss=date(2026, 8, 30),
            nature_of_loss='Fire', loss_location='Site 2', claimed_amount=Decimal('20000.00'),
            status=ClaimStatus.INSPECTION_PENDING, created_by=self.admin_user
        )
        c3 = Claim.objects.create(
            survey_type=self.survey_type, insurer=self.insurer, insured=self.insured, policy=self.policy,
            instruction_date=date(2026, 9, 3), instruction_source='Email', date_of_loss=date(2026, 8, 30),
            nature_of_loss='Fire', loss_location='Site 3', claimed_amount=Decimal('30000.00'),
            status=ClaimStatus.REPORT_SUBMITTED, created_by=self.admin_user
        )
        c4 = Claim.objects.create(
            survey_type=self.survey_type, insurer=self.insurer, insured=self.insured, policy=self.policy,
            instruction_date=date(2026, 9, 4), instruction_source='Email', date_of_loss=date(2026, 8, 30),
            nature_of_loss='Fire', loss_location='Site 4', claimed_amount=Decimal('40000.00'),
            status=ClaimStatus.CLOSED, created_by=self.admin_user
        )

        # In Progress: status NOT IN [NEW, CLOSED, CANCELLED] -> c2 and c3 (REPORT_SUBMITTED) should match
        resp = self.client.get('/claims/?filter=in_progress')
        self.assertEqual(resp.status_code, 200)
        claims = list(resp.context['page_obj'])
        self.assertIn(c2, claims)
        self.assertIn(c3, claims)
        self.assertNotIn(c1, claims)
        self.assertNotIn(c4, claims)

    def test_minimal_claim_detail_view(self):
        """Verify /claims/<id>/ renders read-only summary card."""
        self.client.force_login(self.admin_user)
        claim = Claim.objects.create(
            survey_type=self.survey_type, insurer=self.insurer, insured=self.insured, policy=self.policy,
            instruction_date=date(2026, 9, 1), instruction_source='Email', date_of_loss=date(2026, 8, 30),
            nature_of_loss='Fire', loss_location='Factory A', claimed_amount=Decimal('10000.00'),
            status=ClaimStatus.ASSIGNED, created_by=self.admin_user
        )
        resp = self.client.get(f'/claims/{claim.id}/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, claim.claim_number)
        self.assertContains(resp, self.insurer.company_name)
        self.assertContains(resp, self.insured.name)

    def test_insurer_crud_views(self):
        """Verify Insurer list, add, and edit views."""
        self.client.force_login(self.admin_user)

        # List
        resp = self.client.get('/insurers/')
        self.assertEqual(resp.status_code, 200)

        # Add
        post_data = {
            'company_name': 'New Star Insurance',
            'branch_name': 'South Wing',
            'contact_person': 'Bob Ray',
            'phone': '555-4444',
            'email': 'bob@newstar.test',
            'address': '77 River Way',
            'city': 'Riverdale',
            'state': 'State',
            'pincode': '500001',
            'is_active': 'on'
        }
        resp = self.client.post('/insurers/add/', data=post_data)
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Insurer.objects.filter(company_name='New Star Insurance').exists())

        # Edit
        ins = Insurer.objects.get(company_name='New Star Insurance')
        edit_data = post_data.copy()
        edit_data['contact_person'] = 'Robert Ray'
        resp = self.client.post(f'/insurers/{ins.id}/edit/', data=edit_data)
        self.assertEqual(resp.status_code, 302)
        ins.refresh_from_db()
        self.assertEqual(ins.contact_person, 'Robert Ray')

    def test_insured_crud_views(self):
        """Verify Insured list, add, and edit views."""
        self.client.force_login(self.admin_user)

        # List
        resp = self.client.get('/insured/')
        self.assertEqual(resp.status_code, 200)

        # Add
        post_data = {
            'name': 'Zenith Logistics Ltd',
            'company_name': 'Zenith Corp',
            'contact_person': 'Zack Taylor',
            'phone': '555-8888',
            'email': 'zack@zenith.test',
            'address': '89 Cargo Lane',
            'city': 'Metro City',
            'state': 'State',
            'pincode': '400005',
            'is_active': 'on'
        }
        resp = self.client.post('/insured/add/', data=post_data)
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Insured.objects.filter(name='Zenith Logistics Ltd').exists())

    def test_policy_crud_views(self):
        """Verify Policy list, add, and edit views."""
        self.client.force_login(self.admin_user)

        # List
        resp = self.client.get('/policies/')
        self.assertEqual(resp.status_code, 200)

        # Add
        post_data = {
            'insurer': self.insurer.id,
            'policy_number': 'POL-CRUD-0099',
            'policy_type': 'Engineering All Risk',
            'start_datetime': '2026-09-01T00:00',
            'end_datetime': '2027-09-01T00:00',
            'sum_insured': '5000000.00',
            'excess': '10000.00',
            'commodity': 'Boilers & Generators',
            'subject_matter': 'Power Generation Facility',
            'remarks': 'Annual policy'
        }
        resp = self.client.post('/policies/add/', data=post_data)
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Policy.objects.filter(policy_number='POL-CRUD-0099').exists())

    def test_surveyor_crud_views(self):
        """Verify Surveyor list, add, edit, and workload views."""
        self.client.force_login(self.admin_user)

        # List
        resp = self.client.get('/surveyors/')
        self.assertEqual(resp.status_code, 200)

        # Workload
        resp = self.client.get('/surveyors/workload/')
        self.assertEqual(resp.status_code, 200)

        # Add Surveyor
        post_data = {
            'username': 'new_field_surveyor',
            'email': 'new_surveyor@portal.test',
            'first_name': 'Field',
            'last_name': 'Inspector',
            'password': 'password1234',
            'license_number': 'SLA-TEST-5555',
            'license_expiry': '2028-12-31',
            'phone': '555-7777',
            'specialization': 'Marine Cargo',
            'address': 'Surveyor Office, Port Area'
        }
        resp = self.client.post('/surveyors/add/', data=post_data)
        self.assertEqual(resp.status_code, 302)
        new_surveyor = User.objects.get(username='new_field_surveyor')
        self.assertEqual(new_surveyor.role, User.Role.SURVEYOR)
        self.assertEqual(new_surveyor.surveyor_profile.license_number, 'SLA-TEST-5555')

    def test_supporting_views(self):
        """Verify documents, reports, master data, users, and audit views."""
        self.client.force_login(self.admin_user)
        for url in ['/documents/', '/reports/', '/master/survey-types/', '/master/document-types/', '/master/claim-statuses/', '/users/', '/audit/']:
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 200, f"Failed on {url}")
