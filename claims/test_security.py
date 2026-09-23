from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO
from PIL import Image

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError, PermissionDenied
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APIClient

from surveys.models import SurveyType, Inspection, InspectionPhoto
from claims.models import Insurer, Insured, Policy, Claim, ClaimStatus, SurveyAssignment
from documents.models import DocumentType, ClaimDocument
from assessments.models import Invoice
from reports.models import AuditLog
from documents.validators import validate_document_file, validate_image_file, validate_file_size

User = get_user_model()


def generate_test_image(filename="photo.jpg"):
    stream = BytesIO()
    img = Image.new("RGB", (50, 50), color=(10, 20, 30))
    img.save(stream, format="JPEG")
    stream.seek(0)
    return SimpleUploadedFile(filename, stream.read(), content_type="image/jpeg")


def generate_test_pdf(filename="doc.pdf"):
    content = b"%PDF-1.4 test document content %%EOF"
    return SimpleUploadedFile(filename, content, content_type="application/pdf")


class SecurityHardeningTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username='sec_admin',
            email='admin@sec.test',
            password='ComplexPassword123!',
            role=User.Role.ADMIN
        )
        self.surveyor = User.objects.create_user(
            username='sec_surveyor',
            email='surveyor@sec.test',
            password='ComplexPassword123!',
            role=User.Role.SURVEYOR
        )
        self.unassigned_surveyor = User.objects.create_user(
            username='sec_other_surveyor',
            email='other@sec.test',
            password='ComplexPassword123!',
            role=User.Role.SURVEYOR
        )

        self.st = SurveyType.objects.get(code='FIRE')
        self.insurer = Insurer.objects.create(
            company_name='Security Insurer Corp',
            branch_name='HQ',
            contact_person='Agent Smith',
            phone='+1-555-9999',
            email='claims@secinsurer.com',
            address='123 Security Blvd',
            city='SafeCity',
            state='State',
            pincode='123456'
        )
        self.insured = Insured.objects.create(
            name='Secure Logistics Ltd',
            company_name='Secure Logistics',
            contact_person='John Doe',
            phone='+1-555-8888',
            email='contact@securelogistics.com',
            address='Plot 1 Safe Zone',
            city='SafeCity',
            state='State',
            pincode='123456'
        )
        now = timezone.now()
        self.policy = Policy.objects.create(
            insurer=self.insurer,
            policy_number='POL-SEC-001',
            policy_type='All Risk',
            start_datetime=now - timedelta(days=10),
            end_datetime=now + timedelta(days=355),
            sum_insured=Decimal('1000000.00'),
            excess=Decimal('5000.00'),
            commodity='Electronics',
            subject_matter='Warehouse stock'
        )
        self.claim = Claim.objects.create(
            claim_number='CLM-SEC-001',
            survey_type=self.st,
            insurer=self.insurer,
            insured=self.insured,
            policy=self.policy,
            instruction_date=date(2026, 9, 10),
            instruction_source='Official Email',
            date_of_loss=date(2026, 9, 8),
            nature_of_loss='Water leak in storeroom',
            loss_location='Plot 1 Safe Zone',
            claimed_amount=Decimal('50000.00'),
            status=ClaimStatus.ASSIGNED,
            created_by=self.admin
        )
        self.assignment = SurveyAssignment.objects.create(
            claim=self.claim,
            surveyor=self.surveyor,
            assigned_by=self.admin,
            due_date=date(2026, 9, 25),
            status=SurveyAssignment.Status.ASSIGNED
        )

        # Create files for Secure Media View tests:
        # 1. ClaimDocument
        doc_type, _ = DocumentType.objects.get_or_create(code='GEN_DOC', defaults={'name': 'General Document', 'is_active': True})
        self.claim_doc = ClaimDocument.objects.create(
            claim=self.claim,
            document_type=doc_type,
            file=generate_test_pdf('claim_test_doc.pdf'),
            uploaded_by=self.surveyor
        )

        # 2. InspectionPhoto
        self.inspection = Inspection.objects.create(
            claim=self.claim,
            surveyor=self.surveyor,
            inspection_date=date(2026, 9, 11),
            start_time='09:00',
            end_time='11:00',
            location='Plot 1 Safe Zone',
            person_contacted='John Doe',
            contact_number='+1-555-8888',
            status=Inspection.Status.COMPLETED
        )
        self.photo = InspectionPhoto.objects.create(
            inspection=self.inspection,
            image=generate_test_image('inspection_test_photo.jpg'),
            uploaded_by=self.surveyor
        )

        # 3. Invoice Document
        self.invoice = Invoice.objects.create(
            claim=self.claim,
            invoice_number='INV-2026-001',
            invoice_date=date(2026, 9, 12),
            vendor_name='Repairs Inc',
            amount=Decimal('5000.00'),
            total_amount=Decimal('5000.00'),
            document=generate_test_pdf('invoice_test_doc.pdf')
        )

    # 1. CSRF Enforcement Tests
    def test_csrf_enforcement_on_html_views(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.surveyor)

        # POST without CSRF token must be rejected with 403 Forbidden
        response = client.post(f'/claims/{self.claim.id}/lor/add/', data={'description': 'Test Req'})
        self.assertEqual(response.status_code, 403)

    def test_csrf_enforcement_on_session_authenticated_drf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)

        # POST to DRF API via SessionAuthentication without CSRF token must return 403
        response = client.post(f'/api/claims/{self.claim.id}/close/', data={}, content_type='application/json')
        self.assertEqual(response.status_code, 403)

    # 2. Autoescaping Tests
    def test_template_autoescaping_timeline(self):
        client = Client()
        client.force_login(self.admin)

        # Create status history with potential XSS markup in remarks
        from claims.models import ClaimStatusHistory
        ClaimStatusHistory.objects.create(
            claim=self.claim,
            old_status="NEW",
            new_status="ASSIGNED",
            changed_by=self.admin,
            remarks="<script>alert('xss')</script>"
        )

        response = client.get(f'/claims/{self.claim.id}/?tab=activity')
        self.assertEqual(response.status_code, 200)
        # Content must be HTML escaped, not raw executable script
        self.assertContains(response, "&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;")
        self.assertNotContains(response, "<script>alert('xss')</script>")

    # 3. Secure Media View Tests
    def test_secure_media_anonymous_access_denied(self):
        client = Client()
        # Anonymous user requesting a claim document must be redirected to login
        response = client.get(f'/media/{self.claim_doc.file.name}')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_secure_media_unassigned_surveyor_denied(self):
        client = Client()
        client.force_login(self.unassigned_surveyor)

        # Unassigned surveyor must receive 403 Forbidden on claim document
        response = client.get(f'/media/{self.claim_doc.file.name}')
        self.assertEqual(response.status_code, 403)

        # Unassigned surveyor must receive 403 Forbidden on inspection photo
        response = client.get(f'/media/{self.photo.image.name}')
        self.assertEqual(response.status_code, 403)

        # Unassigned surveyor must receive 403 Forbidden on invoice document
        response = client.get(f'/media/{self.invoice.document.name}')
        self.assertEqual(response.status_code, 403)

    def test_secure_media_assigned_surveyor_allowed_all_three(self):
        client = Client()
        client.force_login(self.surveyor)

        # 1. ClaimDocument -> 200 and streamed via FileResponse
        response_doc = client.get(f'/media/{self.claim_doc.file.name}')
        self.assertEqual(response_doc.status_code, 200)
        self.assertEqual(response_doc['Content-Type'], 'application/pdf')
        self.assertIn(b'%PDF-1.4', response_doc.getvalue())

        # 2. InspectionPhoto -> 200 and streamed via FileResponse
        response_photo = client.get(f'/media/{self.photo.image.name}')
        self.assertEqual(response_photo.status_code, 200)
        self.assertEqual(response_photo['Content-Type'], 'image/jpeg')
        self.assertTrue(len(response_photo.getvalue()) > 0)

        # 3. Invoice Document -> 200 and streamed via FileResponse
        response_inv = client.get(f'/media/{self.invoice.document.name}')
        self.assertEqual(response_inv.status_code, 200)
        self.assertEqual(response_inv['Content-Type'], 'application/pdf')
        self.assertIn(b'%PDF-1.4', response_inv.getvalue())

    def test_secure_media_admin_allowed_all_three(self):
        client = Client()
        client.force_login(self.admin)

        response_doc = client.get(f'/media/{self.claim_doc.file.name}')
        self.assertEqual(response_doc.status_code, 200)

        response_photo = client.get(f'/media/{self.photo.image.name}')
        self.assertEqual(response_photo.status_code, 200)

        response_inv = client.get(f'/media/{self.invoice.document.name}')
        self.assertEqual(response_inv.status_code, 200)

    def test_secure_media_nonexistent_or_traversal(self):
        client = Client()
        client.force_login(self.admin)

        # Non-existent file
        response = client.get('/media/nonexistent/file.pdf')
        self.assertEqual(response.status_code, 404)

        # Directory traversal attempt
        response = client.get('/media/../../settings.py')
        self.assertEqual(response.status_code, 404)

    # 4. Centralized File Upload Validation Tests
    def test_centralized_file_validators(self):
        # Disallowed executable extension
        bad_file = SimpleUploadedFile("malware.exe", b"binary content", content_type="application/x-msdownload")
        with self.assertRaises(ValidationError):
            validate_document_file(bad_file)
        with self.assertRaises(ValidationError):
            validate_image_file(bad_file)

        # Oversized file (> 10MB)
        huge_content = b"x" * (11 * 1024 * 1024)
        huge_file = SimpleUploadedFile("huge.pdf", huge_content, content_type="application/pdf")
        with self.assertRaises(ValidationError):
            validate_file_size(huge_file)

        # Valid pdf and jpg pass
        valid_pdf = SimpleUploadedFile("good.pdf", b"small content", content_type="application/pdf")
        valid_jpg = SimpleUploadedFile("good.jpg", b"small content", content_type="image/jpeg")
        validate_document_file(valid_pdf)
        validate_document_file(valid_jpg)
        validate_image_file(valid_jpg)

    # 5. Password Validation & PBKDF2 Hashing Tests
    def test_password_validation_and_hashing(self):
        # Short password fails
        with self.assertRaises(ValidationError):
            validate_password("short", user=self.admin)

        # Numeric password fails
        with self.assertRaises(ValidationError):
            validate_password("1234567890", user=self.admin)

        # Verify password hasher is PBKDF2
        self.assertTrue(self.admin.password.startswith('pbkdf2_sha256$'))

    # 6. JWT Lifetime & Token Blacklist Tests
    def test_jwt_short_lived_and_logout_blacklisting(self):
        api_client = APIClient()

        # Login to obtain access and refresh tokens
        login_resp = api_client.post('/api/auth/login/', {
            'username': 'sec_surveyor',
            'password': 'ComplexPassword123!'
        })
        self.assertEqual(login_resp.status_code, 200)
        access_token = login_resp.data['access']
        refresh_token = login_resp.data['refresh']
        self.assertIsNotNone(access_token)
        self.assertIsNotNone(refresh_token)

        # Authenticated call with access token succeeds
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')
        me_resp = api_client.get('/api/auth/me/')
        self.assertEqual(me_resp.status_code, 200)

        # Logout by blacklisting refresh token
        logout_resp = api_client.post('/api/auth/logout/', {'refresh': refresh_token})
        self.assertEqual(logout_resp.status_code, 200)

        # Subsequent attempt to refresh using the blacklisted token must fail
        refresh_resp = api_client.post('/api/auth/token/refresh/', {'refresh': refresh_token})
        self.assertEqual(refresh_resp.status_code, 401)

    # 7. Login Rate Limiting Tests
    def test_login_rate_limiting(self):
        api_client = APIClient()
        responses = []
        for _ in range(7):
            resp = api_client.post('/api/auth/login/', {
                'username': 'nonexistent',
                'password': 'WrongPassword123'
            }, REMOTE_ADDR='192.168.1.50')
            responses.append(resp.status_code)

        # At least one request after 5 attempts should return 429 Too Many Requests
        self.assertIn(429, responses)

    # 8. AuditLog IP Address Tracking Tests
    def test_audit_log_records_client_ip(self):
        client = Client()
        client.force_login(self.surveyor)

        # Set claim status to FSR_PREPARED so transition to REPORT_SUBMITTED is valid
        self.claim.status = ClaimStatus.FSR_PREPARED
        self.claim.save()

        # Perform an action that creates an AuditLog (e.g. submit FSR draft)
        from reports.models import FSR, ReportStatus
        fsr = FSR.objects.create(
            claim=self.claim,
            report_number='FSR-SEC-001',
            report_date=date(2026, 9, 15),
            prepared_by=self.surveyor,
            status=ReportStatus.DRAFT,
            introduction='Intro',
            occurrence_details='Occ',
            survey_details='Surv',
            extent_of_loss='Ext',
            cause_of_loss='Cause',
            value_at_risk=Decimal('100000.00'),
            sum_insured=Decimal('100000.00'),
            insured_claim_description='Claim',
            admissibility='Adm',
            policy_coverage='Cov',
            final_opinion='Op'
        )

        response = client.post(
            f'/claims/{self.claim.id}/report/fsr/submit/',
            follow=True,
            REMOTE_ADDR='203.0.113.195'
        )
        self.assertEqual(response.status_code, 200)

        # Verify latest AuditLog entry for this claim has the client IP recorded
        latest_log = AuditLog.objects.filter(claim=self.claim).latest('timestamp')
        self.assertEqual(latest_log.ip_address, '203.0.113.195')
