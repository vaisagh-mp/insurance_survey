from datetime import date
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from accounts.models import SurveyorProfile
from accounts.permissions import IsAssignedSurveyorOrAdmin
from surveys.models import SurveyType
from claims.models import Insurer, Insured, Policy, Claim, SurveyAssignment, Priority, ClaimStatus

User = get_user_model()


class RootViewTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_root_page_redirects_to_login(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/login/')

        # Follow redirect to login page
        follow_response = self.client.get('/', follow=True)
        self.assertEqual(follow_response.status_code, 200)
        self.assertTemplateUsed(follow_response, 'login.html')

    def test_api_schema_endpoint(self):
        response = self.client.get('/api/schema/')
        self.assertEqual(response.status_code, 200)

    def test_api_docs_endpoint(self):
        response = self.client.get('/api/docs/')
        self.assertEqual(response.status_code, 200)

    def test_header_links_hidden(self):
        response = self.client.get('/login/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<li style="display: none;"><a href="/dashboard/admin/">Admin Portal</a></li>', html=True)
        self.assertContains(response, '<li style="display: none;"><a href="/api/docs/">API Docs</a></li>', html=True)
        self.assertContains(response, '<li style="display: none;"><a href="/admin/">Django Admin</a></li>', html=True)


class AccountsModelTests(TestCase):
    def test_user_roles(self):
        admin = User.objects.create_user(
            username='admin_test',
            email='admin@test.com',
            password='password123',
            role=User.Role.ADMIN
        )
        surveyor = User.objects.create_user(
            username='surveyor_test',
            email='surveyor@test.com',
            password='password123',
            role=User.Role.SURVEYOR
        )

        self.assertTrue(admin.is_admin_role)
        self.assertFalse(admin.is_surveyor_role)
        self.assertTrue(surveyor.is_surveyor_role)
        self.assertFalse(surveyor.is_admin_role)

    def test_surveyor_profile_creation(self):
        user = User.objects.create_user(
            username='surveyor_profile_test',
            email='surveyor_profile@test.com',
            password='password123',
            role=User.Role.SURVEYOR
        )
        profile = SurveyorProfile.objects.create(
            user=user,
            license_number='LIC-TEST-001',
            license_expiry=date(2027, 6, 30),
            phone='+1-555-0100',
            address='123 Test Street',
            specialization='Fire & Property'
        )

        self.assertEqual(user.surveyor_profile, profile)
        self.assertEqual(profile.license_number, 'LIC-TEST-001')
        self.assertIn('LIC-TEST-001', str(profile))


class AuthAndPermissionsAPITests(APITestCase):
    def setUp(self):
        # Create Admin
        self.admin_user = User.objects.create_user(
            username='admin_boss',
            email='boss@admin.test',
            password='Password123!',
            role=User.Role.ADMIN
        )

        # Create Surveyor A
        self.surveyor_a = User.objects.create_user(
            username='surveyor_a',
            email='a@surveyor.test',
            password='Password123!',
            role=User.Role.SURVEYOR
        )
        self.profile_a = SurveyorProfile.objects.create(
            user=self.surveyor_a,
            license_number='LIC-A-100',
            license_expiry=date(2028, 1, 1),
            phone='+1-555-1001',
            address='Surveyor Office A',
            specialization='Marine Cargo'
        )

        # Create Surveyor B
        self.surveyor_b = User.objects.create_user(
            username='surveyor_b',
            email='b@surveyor.test',
            password='Password123!',
            role=User.Role.SURVEYOR
        )
        self.profile_b = SurveyorProfile.objects.create(
            user=self.surveyor_b,
            license_number='LIC-B-200',
            license_expiry=date(2028, 1, 1),
            phone='+1-555-2002',
            address='Surveyor Office B',
            specialization='Fire & Engineering'
        )

        # Create shared master records
        self.survey_type = SurveyType.objects.get(code='MARINE')
        self.insurer = Insurer.objects.create(
            company_name='Atlas Insurance',
            branch_name='Main Branch',
            address='100 Atlas Plaza',
            city='Metro',
            state='State',
            pincode='400001',
            contact_person='Atlas Officer',
            phone='+1-555-3001',
            email='claims@atlas.test'
        )
        self.insured = Insured.objects.create(
            name='Oceanic Traders Ltd',
            address='Dock 4',
            city='Metro',
            state='State',
            pincode='400002',
            phone='+1-555-3002',
            email='oceanic@traders.test',
            contact_person='Logistics Manager'
        )
        now = timezone.now()
        self.policy = Policy.objects.create(
            insurer=self.insurer,
            policy_number='POL-ATL-2026-01',
            policy_type='Marine Policy',
            start_datetime=now,
            end_datetime=now + timezone.timedelta(days=365),
            sum_insured=Decimal('10000000.00'),
            excess=Decimal('10000.00'),
            commodity='Bulk Grain Cargo',
            subject_matter='Consignment 1'
        )

        # Create Claim 1 (Assigned to Surveyor A)
        self.claim_1 = Claim.objects.create(
            survey_type=self.survey_type,
            insurer=self.insurer,
            insured=self.insured,
            policy=self.policy,
            instruction_date=date(2026, 9, 10),
            instruction_source='Email',
            date_of_loss=date(2026, 9, 8),
            nature_of_loss='Grain moisture damage',
            loss_location='Silo 1',
            claimed_amount=Decimal('500000.00'),
            priority=Priority.MEDIUM,
            status=ClaimStatus.ASSIGNED,
            created_by=self.admin_user
        )
        SurveyAssignment.objects.create(
            claim=self.claim_1,
            surveyor=self.surveyor_a,
            assigned_by=self.admin_user,
            due_date=date(2026, 9, 25),
            priority=Priority.MEDIUM,
            status=SurveyAssignment.Status.ASSIGNED
        )

        # Create Claim 2 (Assigned to Surveyor B)
        self.claim_2 = Claim.objects.create(
            survey_type=self.survey_type,
            insurer=self.insurer,
            insured=self.insured,
            policy=self.policy,
            instruction_date=date(2026, 9, 11),
            instruction_source='Email',
            date_of_loss=date(2026, 9, 9),
            nature_of_loss='Container dent and leak',
            loss_location='Container Yard 2',
            claimed_amount=Decimal('300000.00'),
            priority=Priority.HIGH,
            status=ClaimStatus.ASSIGNED,
            created_by=self.admin_user
        )
        SurveyAssignment.objects.create(
            claim=self.claim_2,
            surveyor=self.surveyor_b,
            assigned_by=self.admin_user,
            due_date=date(2026, 9, 25),
            priority=Priority.HIGH,
            status=SurveyAssignment.Status.ASSIGNED
        )

    def test_jwt_login_success(self):
        url = '/api/auth/login/'
        payload = {'username': 'surveyor_a', 'password': 'Password123!'}
        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)
        self.assertEqual(response.data['user']['role'], 'SURVEYOR')

    def test_jwt_login_failure(self):
        url = '/api/auth/login/'
        payload = {'username': 'surveyor_a', 'password': 'WrongPassword!'}
        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_jwt_logout_blacklists_token(self):
        # Obtain tokens
        refresh = RefreshToken.for_user(self.surveyor_a)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')

        logout_url = '/api/auth/logout/'
        response = self.client.post(logout_url, {'refresh': str(refresh)})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['detail'], 'Successfully logged out.')

        # Attempt to refresh using blacklisted token
        refresh_url = '/api/auth/token/refresh/'
        refresh_resp = self.client.post(refresh_url, {'refresh': str(refresh)})
        self.assertEqual(refresh_resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_auth_me_endpoint_for_admin_and_surveyor(self):
        # Admin /api/auth/me/
        token_admin = RefreshToken.for_user(self.admin_user).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token_admin}')
        resp_admin = self.client.get('/api/auth/me/')
        self.assertEqual(resp_admin.status_code, status.HTTP_200_OK)
        self.assertEqual(resp_admin.data['username'], 'admin_boss')
        self.assertEqual(resp_admin.data['role'], 'ADMIN')
        self.assertIsNone(resp_admin.data['surveyor_profile'])

        # Surveyor /api/auth/me/
        token_surv = RefreshToken.for_user(self.surveyor_a).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token_surv}')
        resp_surv = self.client.get('/api/auth/me/')
        self.assertEqual(resp_surv.status_code, status.HTTP_200_OK)
        self.assertEqual(resp_surv.data['username'], 'surveyor_a')
        self.assertEqual(resp_surv.data['role'], 'SURVEYOR')
        self.assertIsNotNone(resp_surv.data['surveyor_profile'])
        self.assertEqual(resp_surv.data['surveyor_profile']['license_number'], 'LIC-A-100')

    def test_surveyor_a_can_get_their_own_assigned_claim(self):
        token_a = RefreshToken.for_user(self.surveyor_a).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token_a}')

        # Requesting own claim (Claim 1)
        response = self.client.get(f'/api/claims/{self.claim_1.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], self.claim_1.id)
        self.assertEqual(response.data['claim_number'], self.claim_1.claim_number)

    def test_surveyor_a_gets_403_or_404_requesting_surveyor_b_claim(self):
        token_a = RefreshToken.for_user(self.surveyor_a).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token_a}')

        # Requesting Surveyor B's claim (Claim 2) by ID
        response = self.client.get(f'/api/claims/{self.claim_2.id}/')
        # Blocked: must return 403 Forbidden or 404 Not Found (not the data)
        self.assertIn(response.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND])
        self.assertNotIn('claim_number', response.data)

    def test_admin_can_get_any_claim(self):
        token_admin = RefreshToken.for_user(self.admin_user).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token_admin}')

        # Admin requesting Claim 1
        resp_1 = self.client.get(f'/api/claims/{self.claim_1.id}/')
        self.assertEqual(resp_1.status_code, status.HTTP_200_OK)
        self.assertEqual(resp_1.data['id'], self.claim_1.id)

        # Admin requesting Claim 2
        resp_2 = self.client.get(f'/api/claims/{self.claim_2.id}/')
        self.assertEqual(resp_2.status_code, status.HTTP_200_OK)
        self.assertEqual(resp_2.data['id'], self.claim_2.id)

    def test_surveyor_claim_list_scoped(self):
        token_a = RefreshToken.for_user(self.surveyor_a).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token_a}')

        resp = self.client.get('/api/claims/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        results = resp.data.get('results', resp.data)
        ids = [item['id'] for item in results]
        self.assertIn(self.claim_1.id, ids)
        self.assertNotIn(self.claim_2.id, ids)

    def test_reassigned_claim_access_blocked_for_old_surveyor(self):
        """
        Test that when a claim is reassigned from Surveyor A to Surveyor B:
        - Surveyor A can initially GET the claim (200).
        - After setting Surveyor A's assignment to REASSIGNED and creating
          a new assignment for Surveyor B:
          - Surveyor A gets 403/404.
          - Surveyor B gets 200.
        """
        # 1. Surveyor A is assigned to self.claim_1 and can GET it
        token_a = RefreshToken.for_user(self.surveyor_a).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token_a}')
        resp_a_before = self.client.get(f'/api/claims/{self.claim_1.id}/')
        self.assertEqual(resp_a_before.status_code, status.HTTP_200_OK)
        self.assertEqual(resp_a_before.data['id'], self.claim_1.id)

        # 2. Reassign the claim to Surveyor B
        old_assignment = SurveyAssignment.objects.get(claim=self.claim_1, surveyor=self.surveyor_a)
        old_assignment.status = SurveyAssignment.Status.REASSIGNED
        old_assignment.save()

        SurveyAssignment.objects.create(
            claim=self.claim_1,
            surveyor=self.surveyor_b,
            assigned_by=self.admin_user,
            due_date=date(2026, 9, 30),
            priority=Priority.HIGH,
            status=SurveyAssignment.Status.ASSIGNED
        )

        # Direct verification of IsAssignedSurveyorOrAdmin permission check
        permission = IsAssignedSurveyorOrAdmin()
        request_mock_a = type('Request', (), {'user': self.surveyor_a})()
        request_mock_b = type('Request', (), {'user': self.surveyor_b})()
        self.assertFalse(permission.has_object_permission(request_mock_a, None, self.claim_1))
        self.assertTrue(permission.has_object_permission(request_mock_b, None, self.claim_1))

        # 3. Confirm Surveyor A now gets 403 or 404 (not the data)
        resp_a_after = self.client.get(f'/api/claims/{self.claim_1.id}/')
        self.assertIn(resp_a_after.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND])
        self.assertNotIn('claim_number', resp_a_after.data)

        # 4. Confirm Surveyor B gets 200
        token_b = RefreshToken.for_user(self.surveyor_b).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token_b}')
        resp_b = self.client.get(f'/api/claims/{self.claim_1.id}/')
        self.assertEqual(resp_b.status_code, status.HTTP_200_OK)
        self.assertEqual(resp_b.data['id'], self.claim_1.id)

