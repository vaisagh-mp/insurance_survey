# Insurance Survey System — Project Structure & Architecture

> **Snapshot Date:** September 2026  
> **Django Version:** 5.x | **DRF:** 3.15.x | **Database:** SQLite (Dev) / PostgreSQL (Prod)  
> **Status:** Fully Functional (169 passing unit and integration tests)

---

## 1. Directory Tree & App Overview

```text
insurance_survey/
│
├── manage.py                          # Django management script
├── requirements.txt                   # Project dependencies (Django, DRF, WeasyPrint, SimpleJWT, Pillow, etc.)
├── db.sqlite3                         # Local development database
│
├── config/                            # Core project configuration & root routing
│   ├── settings/
│   │   ├── __init__.py
│   │   ├── base.py                    # Shared settings, apps, auth, JWT, firm profile, WeasyPrint config
│   │   ├── dev.py                     # Local development settings (DEBUG=True, SQLite)
│   │   └── prod.py                    # Production settings (DEBUG=False, PostgreSQL, security headers)
│   ├── urls.py                        # Root URL configuration (Web portal, API v1, Admin, Media)
│   ├── wsgi.py                        # WSGI entry point for synchronous web servers (Gunicorn)
│   └── asgi.py                        # ASGI entry point for async servers
│
├── accounts/                          # App: Authentication, custom User model, surveyor profiles & permissions
│   ├── models.py                      # User (with ADMIN/SURVEYOR roles), SurveyorProfile
│   ├── forms.py                       # WebLoginForm, SurveyorCreateForm, SurveyorUpdateForm
│   ├── views.py                       # DRF LoginView, LogoutView, MeView, LoginRateThrottle
│   ├── permissions.py                 # IsAdminUserRole, IsSurveyorUserRole, IsAssignedSurveyorOrAdmin
│   ├── serializers.py                 # User and profile serializers
│   ├── urls.py                        # API authentication endpoints (/api/auth/*)
│   ├── admin.py                       # Django Admin registration for Users and Profiles
│   ├── tests.py                       # Accounts and authentication tests
│   └── migrations/                    # 3 migrations
│
├── claims/                            # App: Claim lifecycle, master entities (Insurer/Insured/Policy), assignments
│   ├── models.py                      # Insurer, Insured, Policy, Claim, ClaimStatusHistory, SurveyAssignment
│   ├── services.py                    # State transitions (ALLOWED_TRANSITIONS), assignments, queries, closing
│   ├── forms.py                       # ClaimCreateForm, InsurerForm, InsuredForm, PolicyForm, LOB Detail forms
│   ├── web_views.py                   # Server-side views for Web UI (dashboards, claim tabs, masters, users)
│   ├── web_urls.py                    # URL routing for Web UI (/claims/*, /insurers/*, /policies/*, etc.)
│   ├── views.py                       # DRF ClaimViewSet, InsurerViewSet, InsuredViewSet, PolicyViewSet
│   ├── urls.py                        # DRF API routing (/api/claims/*, etc.)
│   ├── serializers.py                 # Claim, Insurer, Insured, Policy serializers
│   ├── admin.py                       # Django Admin models registration
│   ├── tests.py                       # Claim workflow unit tests
│   ├── test_web.py                    # Web portal view tests
│   ├── test_surveyor_web.py           # Surveyor role portal access and authorization tests
│   ├── test_business_workflows.py     # End-to-end claim lifecycle tests
│   ├── test_security.py               # Security and permission boundary tests
│   ├── test_html_forms.py             # Form validation tests
│   └── migrations/                    # 5 migrations
│
├── surveys/                           # App: Inspections, photos, observations & line-of-business (LOB) details
│   ├── models.py                      # SurveyType, Inspection, InspectionPhoto, InspectionObservation,
│   │                                  # FireClaimDetails, EngineeringClaimDetails, MarineClaimDetails, PropertyClaimDetails
│   ├── services.py                    # complete_inspection service function
│   ├── forms.py                       # InspectionForm, MultipleFileInput, MultipleFileField
│   ├── validators.py                  # Inspection image format and size validation
│   ├── views.py                       # DRF SurveyTypeViewSet, InspectionViewSet
│   ├── urls.py                        # DRF API routing (/api/inspections/*, /api/survey-types/*)
│   ├── serializers.py                 # Inspection and LOB detail serializers
│   ├── admin.py                       # Survey models Django Admin registration
│   ├── tests.py                       # Inspection and photo upload tests
│   └── migrations/                    # 6 migrations
│
├── assessments/                       # App: Financial loss calculation, line-item BOQs & repair loss invoices
│   ├── models.py                      # Invoice (loss evidence), Assessment, AssessmentItem
│   ├── services.py                    # recalculate_assessment, round_curr helper
│   ├── forms.py                       # AssessmentFinancialForm, AssessmentItemForm, InvoiceForm
│   ├── views.py                       # DRF AssessmentViewSet
│   ├── urls.py                        # DRF API routing (/api/assessments/*)
│   ├── serializers.py                 # Assessment and item serializers
│   ├── admin.py                       # Assessment Django Admin registration
│   ├── tests.py                       # Assessment math, invoice upload, verify & delete tests
│   └── migrations/                    # 4 migrations
│
├── reports/                           # App: Formal survey reports (ILA/ISR/FSR), WeasyPrint PDF engine & AuditLog
│   ├── models.py                      # AuditLog, ILA, ISR, FSR
│   ├── services.py                    # generate_report_pdf, generate_report_number, save_report_pdf_as_document,
│   │                                  # get_soteria_assets, log_action, get_client_ip
│   ├── forms.py                       # ILAForm, ISRForm, FSRForm
│   ├── views.py                       # DRF ILAViewSet, ISRViewSet, FSRViewSet, ReportPdfActionsMixin
│   ├── urls.py                        # DRF API routing (/api/ila/*, /api/isr/*, /api/fsr/*)
│   ├── serializers.py                 # Report serializers
│   ├── admin.py                       # Reports Django Admin registration
│   ├── tests.py                       # Report generation, versioning & PDF rendering tests
│   ├── test_fsr_format.py             # FSR formatting and layout regression tests
│   └── migrations/                    # 5 migrations
│
├── documents/                         # App: Document management, LOR missing requirements & secure file download
│   ├── models.py                      # DocumentType, ClaimDocument, Requirement (LOR item)
│   ├── services.py                    # verify_claim_document, update_requirement_status
│   ├── forms.py                       # ClaimDocumentForm, RequirementForm
│   ├── validators.py                  # File extension and 10MB size limits
│   ├── views.py                       # DRF ClaimDocumentViewSet, RequirementViewSet, secure_media_view
│   ├── urls.py                        # DRF API routing (/api/documents/*, /api/requirements/*)
│   ├── serializers.py                 # Document serializers
│   ├── admin.py                       # Documents Django Admin registration
│   ├── tests.py                       # Document upload, validation & verification tests
│   └── migrations/                    # 3 migrations
│
├── billing/                           # App: Surveyor firm fee invoicing to Insurer, GST calculations & fee PDF
│   ├── models.py                      # ServiceInvoice, ServiceInvoiceItem
│   ├── services.py                    # recalculate_invoice, add/update/delete item, mark_sent, record_payment,
│   │                                  # cancel_invoice, generate_invoice_pdf
│   ├── forms.py                       # ServiceInvoiceForm, ServiceInvoiceItemForm
│   ├── web_views.py                   # Server-side views for Billing Tab (/claims/<pk>/billing/*, /billing/)
│   ├── web_urls.py                    # Billing portal routing
│   ├── views.py                       # API view placeholder
│   ├── urls.py                        # App URL dispatcher
│   ├── admin.py                       # ServiceInvoice Django Admin registration
│   ├── tests.py                       # Service invoice calculation & workflow tests
│   ├── test_billing.py                # Billing integration tests
│   ├── templates/billing/             # invoice_list.html, service_invoice_pdf.html
│   └── migrations/                    # 1 migration
│
├── templates/                         # Global and app HTML templates for the Web UI
│   ├── base.html                      # Main layout (navigation bar, flash messages, user session)
│   ├── home.html                      # Landing page redirecting by role
│   ├── login.html                     # Portal login page
│   ├── audit/                         # Audit log viewer
│   ├── claims/                        # claim_list.html, claim_form.html, claim_detail.html (10-tab workspace)
│   ├── dashboard/                     # admin_dashboard.html, surveyor_dashboard.html
│   ├── documents/                     # document_list.html
│   ├── insured/                       # insured_list.html, insured_form.html
│   ├── insurers/                      # insurer_list.html, insurer_form.html
│   ├── master/                        # master_claim_statuses.html, master_document_types.html, master_survey_types.html
│   ├── policies/                      # policy_list.html, policy_form.html
│   ├── reports/                       # report_list.html, ila_pdf.html, isr_pdf.html, fsr_pdf.html
│   ├── surveyors/                     # surveyor_list.html, surveyor_form.html, surveyor_workload.html
│   └── users/                         # user_list.html
│
├── static/                            # Static assets
│   └── css/
│       └── style.css                  # Modern responsive design stylesheet
│
├── media/                             # Uploaded media (securely protected, not served directly via static)
│   ├── claim_documents/
│   ├── inspection_photos/
│   └── repair_invoices/
│
└── docs/                              # Project documentation
    └── PROJECT_STRUCTURE.md           # This architecture & codebase explanation document
```

---

## 2. App-by-App Specification

### 2.1 Accounts App (`accounts`)
*One-line Purpose:* Manages user accounts, authentication credentials, role-based segregation (`ADMIN` vs `SURVEYOR`), and professional surveyor license profiles.

#### Models & Fields
1. **`User`** (Custom User Model extending `AbstractUser`)
   - `id`: BigAutoField
   - `username`: CharField
   - `password`: CharField
   - `first_name`: CharField
   - `last_name`: CharField
   - `email`: CharField
   - `role`: CharField (`ADMIN`, `SURVEYOR`)
   - `is_staff`: BooleanField
   - `is_active`: BooleanField
   - `is_superuser`: BooleanField
   - `date_joined`: DateTimeField
   - `last_login`: DateTimeField
2. **`SurveyorProfile`**
   - `id`: BigAutoField
   - `user`: OneToOneField (`-> accounts.User`)
   - `license_number`: CharField
   - `license_expiry`: DateField
   - `phone`: CharField
   - `address`: TextField
   - `specialization`: CharField
   - `created_at`: DateTimeField
   - `updated_at`: DateTimeField

#### Key Relationships
- `SurveyorProfile.user` -> `accounts.User` (OneToOne)
- `accounts.User` is referenced as Foreign Key across the entire project (`Claim.created_by`, `SurveyAssignment.surveyor`, `Inspection.surveyor`, `ClaimDocument.uploaded_by`, `ServiceInvoice.created_by`, etc.).

#### Service-Layer Functions
- Handled directly via Django authentication backends, `accounts/forms.py` (`SurveyorCreateForm`, `SurveyorUpdateForm`), and `accounts/permissions.py`.

#### Web Views & URLs
- `web_login`: `/login/` [name: `web_login`]
- `web_logout`: `/logout/` [name: `web_logout`]
- `user_list`: `/users/` [name: `web_user_list`]
- `surveyor_list`: `/surveyors/` [name: `web_surveyor_list`]
- `surveyor_add`: `/surveyors/add/` [name: `web_surveyor_add`]
- `surveyor_edit`: `/surveyors/<int:pk>/edit/` [name: `web_surveyor_edit`]
- `surveyor_workload`: `/surveyors/workload/` [name: `web_surveyor_workload`]

#### DRF API Endpoints
- `POST /api/auth/login/` -> `LoginView` (Rate limited: 5 requests/minute)
- `POST /api/auth/refresh/` -> `TokenRefreshView` (SimpleJWT)
- `POST /api/auth/logout/` -> `LogoutView` (Token blacklist)
- `GET /api/auth/me/` -> `MeView` (Authenticated user profile)

---

### 2.2 Claims App (`claims`)
*One-line Purpose:* Houses the central Claim workflow, master entities (Insurers, Insured parties, Policies), surveyor task assignment, and status state machine audit tracking.

#### Models & Fields
1. **`Insurer`**
   - `id`: BigAutoField
   - `company_name`: CharField
   - `branch_name`: CharField
   - `address`: TextField
   - `city`: CharField
   - `state`: CharField
   - `pincode`: CharField
   - `contact_person`: CharField
   - `phone`: CharField
   - `email`: CharField
   - `gstin`: CharField
   - `is_active`: BooleanField
   - `created_at`: DateTimeField
   - `updated_at`: DateTimeField
2. **`Insured`**
   - `id`: BigAutoField
   - `name`: CharField
   - `company_name`: CharField
   - `address`: TextField
   - `city`: CharField
   - `state`: CharField
   - `pincode`: CharField
   - `phone`: CharField
   - `email`: CharField
   - `gstin`: CharField
   - `contact_person`: CharField
   - `is_active`: BooleanField
   - `created_at`: DateTimeField
   - `updated_at`: DateTimeField
3. **`Policy`**
   - `id`: BigAutoField
   - `insurer`: ForeignKey (`-> claims.Insurer`)
   - `policy_number`: CharField
   - `policy_type`: CharField
   - `start_datetime`: DateTimeField
   - `end_datetime`: DateTimeField
   - `sum_insured`: DecimalField
   - `excess`: DecimalField
   - `commodity`: CharField
   - `subject_matter`: TextField
   - `remarks`: TextField
   - `created_at`: DateTimeField
   - `updated_at`: DateTimeField
4. **`Claim`**
   - `id`: BigAutoField
   - `claim_number`: CharField (Auto-generated unique e.g. `CLM-2026-00001`)
   - `report_number`: CharField
   - `survey_type`: ForeignKey (`-> surveys.SurveyType`)
   - `insurer`: ForeignKey (`-> claims.Insurer`)
   - `insured`: ForeignKey (`-> claims.Insured`)
   - `policy`: ForeignKey (`-> claims.Policy`)
   - `instruction_date`: DateField
   - `instruction_source`: CharField
   - `date_of_loss`: DateField
   - `nature_of_loss`: CharField
   - `loss_location`: TextField
   - `claimed_amount`: DecimalField
   - `priority`: CharField (`LOW`, `MEDIUM`, `HIGH`, `URGENT`)
   - `status`: CharField (17 distinct lifecycle states)
   - `claim_description`: TextField
   - `contact_person`: CharField
   - `contact_phone`: CharField
   - `contact_email`: CharField
   - `internal_remarks`: TextField
   - `created_by`: ForeignKey (`-> accounts.User`)
   - `created_at`: DateTimeField
   - `updated_at`: DateTimeField
5. **`ClaimStatusHistory`**
   - `id`: BigAutoField
   - `claim`: ForeignKey (`-> claims.Claim`)
   - `old_status`: CharField
   - `new_status`: CharField
   - `changed_by`: ForeignKey (`-> accounts.User`)
   - `changed_at`: DateTimeField
   - `remarks`: TextField
6. **`SurveyAssignment`**
   - `id`: BigAutoField
   - `claim`: ForeignKey (`-> claims.Claim`)
   - `surveyor`: ForeignKey (`-> accounts.User`)
   - `assigned_by`: ForeignKey (`-> accounts.User`)
   - `assigned_at`: DateTimeField
   - `due_date`: DateField
   - `priority`: CharField
   - `instructions`: TextField
   - `status`: CharField (`ASSIGNED`, `IN_PROGRESS`, `COMPLETED`, `REASSIGNED`)
   - `remarks`: TextField

#### Key Relationships
- `Claim.survey_type` -> `surveys.SurveyType`
- `Claim.insurer` -> `claims.Insurer`, `Claim.insured` -> `claims.Insured`, `Claim.policy` -> `claims.Policy`
- `Claim.created_by` -> `accounts.User`
- `SurveyAssignment.claim` -> `claims.Claim`, `SurveyAssignment.surveyor` -> `accounts.User`
- OneToOne child models in other apps attach to `Claim`: `FireClaimDetails`, `EngineeringClaimDetails`, `MarineClaimDetails`, `PropertyClaimDetails`, `Assessment`, and `ServiceInvoice`.

#### Service-Layer Functions (`claims/services.py`)
- `transition_claim_status(claim, new_status, changed_by, remarks)`: Validates transition legality against `ALLOWED_TRANSITIONS`, records history in `ClaimStatusHistory`, and saves the claim.
- `assign_surveyor(claim, surveyor, assigned_by, due_date, priority, instructions, remarks)`: Creates or updates `SurveyAssignment` and transitions claim status to `ASSIGNED`.
- `reassign_surveyor(claim, new_surveyor, reassigned_by, due_date, priority, instructions, remarks)`: Closes prior assignment as `REASSIGNED` and creates new assignment with full audit trail.
- `submit_report(report, submitted_by)`: Marks report as `SUBMITTED`, increments version, and transitions claim to `REPORT_SUBMITTED` (or `ILA_PREPARED` / `ISR_PREPARED` / `FSR_PREPARED`).
- `raise_query(claim, raised_by, remarks, report)`: Marks report status as `QUERY` and transitions claim to `QUERY_RAISED`.
- `respond_query(claim, surveyor, remarks, report)`: Reopens report back to `DRAFT` with an incremented version and sets claim status to `RESUBMITTED`.
- `close_claim(claim, closed_by, remarks)`: Validates that an approved final report exists and transitions claim to `CLOSED`.

#### Web Views & URLs
- `admin_dashboard`: `/dashboard/admin/` [name: `admin_dashboard`]
- `surveyor_dashboard`: `/dashboard/surveyor/` [name: `surveyor_dashboard`]
- `claim_list`: `/claims/` [name: `web_claim_list`]
- `claim_create`: `/claims/create/` [name: `web_claim_create`]
- `claim_detail`: `/claims/<int:pk>/` [name: `web_claim_detail`] (10-tab workspace)
- `claim_assign_surveyor`: `/claims/<int:pk>/assign/` [name: `web_claim_assign_surveyor`]
- `claim_approve_and_close`: `/claims/<int:pk>/approve-and-close/` [name: `web_claim_approve_and_close`]
- Insurers CRUD: `/insurers/`, `/insurers/add/`, `/insurers/<int:pk>/edit/`
- Insured CRUD: `/insured/`, `/insured/add/`, `/insured/<int:pk>/edit/`
- Policies CRUD: `/policies/`, `/policies/add/`, `/policies/<int:pk>/edit/`
- Master data: `/master/survey-types/`, `/master/document-types/`, `/master/claim-statuses/`
- Audit trail: `/audit/` [name: `web_audit_list`]

#### DRF API Endpoints
- `GET/POST /api/claims/` (`ClaimViewSet`)
- `GET/PUT/PATCH/DELETE /api/claims/<pk>/`
- `POST /api/claims/<pk>/assign-surveyor/`
- `POST /api/claims/<pk>/reassign-surveyor/`
- `POST /api/claims/<pk>/submit-report/`
- `POST /api/claims/<pk>/raise-query/`
- `POST /api/claims/<pk>/respond-query/`
- `POST /api/claims/<pk>/close/`
- CRUD viewsets for `/api/insurers/`, `/api/insured/`, `/api/policies/`

---

### 2.3 Surveys App (`surveys`)
*One-line Purpose:* Captures on-site physical survey inspections, GPS geo-tagged damage photos, structured observations, and specialized Line-of-Business (LOB) technical claim details.

#### Models & Fields
1. **`SurveyType`**
   - `id`: BigAutoField
   - `name`: CharField
   - `code`: CharField (`FIRE`, `ENG`, `MARINE`, `PROP`)
   - `description`: TextField
   - `is_active`: BooleanField
   - `created_at`: DateTimeField
   - `updated_at`: DateTimeField
2. **`Inspection`**
   - `id`: BigAutoField
   - `claim`: ForeignKey (`-> claims.Claim`)
   - `surveyor`: ForeignKey (`-> accounts.User`)
   - `inspection_date`: DateField
   - `start_time`: TimeField
   - `end_time`: TimeField
   - `location`: CharField
   - `person_contacted`: CharField
   - `contact_number`: CharField
   - `contact_email`: CharField
   - `reason_for_delay`: TextField
   - `site_representative`: CharField
   - `observations`: TextField
   - `extent_of_damage`: TextField
   - `cause_observations`: TextField
   - `salvage_observations`: TextField
   - `status`: CharField (`SCHEDULED`, `IN_PROGRESS`, `COMPLETED`, `CANCELLED`)
   - `created_at`: DateTimeField
   - `updated_at`: DateTimeField
3. **`InspectionPhoto`**
   - `id`: BigAutoField
   - `inspection`: ForeignKey (`-> surveys.Inspection`)
   - `image`: FileField
   - `caption`: CharField
   - `category`: CharField (`OVERVIEW`, `CLOSE_UP`, `DAMAGE`, `SURROUNDINGS`, `OTHER`)
   - `latitude`: DecimalField
   - `longitude`: DecimalField
   - `captured_at`: DateTimeField
   - `uploaded_by`: ForeignKey (`-> accounts.User`)
   - `created_at`: DateTimeField
4. **`InspectionObservation`**
   - `id`: BigAutoField
   - `inspection`: ForeignKey (`-> surveys.Inspection`)
   - `category`: CharField
   - `description`: TextField
   - `severity`: CharField (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`)
   - `created_by`: ForeignKey (`-> accounts.User`)
   - `created_at`: DateTimeField
5. **`FireClaimDetails`**
   - `id`: BigAutoField
   - `claim`: OneToOneField (`-> claims.Claim`)
   - `construction_details`, `occupancy`, `building_description`, `fire_protection_details`: TextField
   - `fire_brigade_informed`: BooleanField, `fire_brigade_details`: TextField
   - `police_informed`: BooleanField, `police_details`: TextField
   - `fire_cause`: TextField, `cause_established`: BooleanField, `point_of_origin`: CharField
   - `storage_details`, `machinery_details`, `stock_details`, `salvage_observation`: TextField
6. **`EngineeringClaimDetails`**
   - `id`: BigAutoField
   - `claim`: OneToOneField (`-> claims.Claim`)
   - `equipment_name`, `manufacturer`, `model`, `serial_number`, `machine_location`: CharField
   - `year_of_manufacture`: PositiveIntegerField, `installation_date`: DateField
   - `breakdown_description`, `damage_description`, `cause_of_breakdown`, `salvage`: TextField
   - `repair_estimate`, `replacement_cost`, `parts_cost`, `labour_cost`, `testing_cost`: DecimalField
7. **`MarineClaimDetails`**
   - `id`: BigAutoField
   - `claim`: OneToOneField (`-> claims.Claim`)
   - `vessel_name`, `voyage_number`, `port_of_loading`, `port_of_discharge`, `place_of_survey`: CharField
   - `consignor`, `consignee`, `carrier`, `bill_of_lading_number`, `container_number`: CharField
   - `package_count`: PositiveIntegerField
   - `cargo_description`, `damage_description`, `transit_details`, `packing_condition`, `salvage_details`: TextField
8. **`PropertyClaimDetails`**
   - `id`: BigAutoField
   - `claim`: OneToOneField (`-> claims.Claim`)
   - `property_type`, `occupancy`, `construction_type`: CharField
   - `building_area`: DecimalField, `number_of_floors`: PositiveIntegerField
   - `building_description`, `contents_description`, `stock_description`, `damage_description`, `salvage`: TextField
   - `repair_estimate`, `replacement_cost`: DecimalField

#### Key Relationships
- `Inspection.claim` -> `claims.Claim`, `InspectionPhoto.inspection` -> `surveys.Inspection`
- `FireClaimDetails`, `EngineeringClaimDetails`, `MarineClaimDetails`, `PropertyClaimDetails` all map `OneToOne` to `claims.Claim`.

#### Service-Layer Functions (`surveys/services.py`)
- `complete_inspection(inspection, observations_data, photos_data)`: Marks inspection completed, saves observations and photos, and transitions claim status to `INSPECTION_COMPLETED`.

#### Web Views & URLs
- `claim_inspection_save`: `/claims/<int:pk>/inspection/save/` [name: `web_claim_inspection_save`]

#### DRF API Endpoints
- `GET/POST /api/survey-types/` (`SurveyTypeViewSet`)
- `GET/POST /api/inspections/` (`InspectionViewSet`)
- `GET /api/claims/<pk>/inspections/` (nested on `ClaimViewSet`)

---

### 2.4 Assessments App (`assessments`)
*One-line Purpose:* Manages itemized loss assessment line items (BOQ), automated financial recalculations (gross loss, depreciation, underinsurance, excess, net loss), and workshop repair loss bills submitted as evidence.

#### Models & Fields
1. **`Invoice`** *(Evidence of loss submitted by insured / repair workshop)*
   - `id`: BigAutoField
   - `claim`: ForeignKey (`-> claims.Claim`)
   - `invoice_number`: CharField
   - `invoice_date`: DateField
   - `vendor_name`: CharField
   - `description`: TextField
   - `amount`: DecimalField (Base amount)
   - `tax_amount`: DecimalField (GST/tax)
   - `total_amount`: DecimalField (amount + tax_amount)
   - `document`: FileField (Uploaded bill/receipt)
   - `verified`: BooleanField
   - `verified_by`: ForeignKey (`-> accounts.User`)
   - `remarks`: TextField
   - `created_at`, `updated_at`: DateTimeField
2. **`Assessment`**
   - `id`: BigAutoField
   - `claim`: OneToOneField (`-> claims.Claim`)
   - `gross_assessed_loss`: DecimalField
   - `salvage_amount`: DecimalField
   - `underinsurance_percentage`: DecimalField
   - `underinsurance_amount`: DecimalField
   - `adjusted_loss`: DecimalField
   - `depreciation_amount`: DecimalField
   - `policy_excess`: DecimalField
   - `other_deductions`: DecimalField
   - `net_assessed_loss`: DecimalField
   - `assessment_remarks`: TextField
   - `created_by`: ForeignKey (`-> accounts.User`)
   - `created_at`, `updated_at`: DateTimeField
3. **`AssessmentItem`**
   - `id`: BigAutoField
   - `assessment`: ForeignKey (`-> assessments.Assessment`)
   - `item_code`: CharField
   - `description`: TextField
   - `specification`: TextField
   - `quantity`: DecimalField
   - `rate`: DecimalField
   - `category`: CharField (`PARTS`, `LABOUR`, `PAINTING`, `DISMANTLING`, `OTHER`)
   - `claimed_amount`: DecimalField
   - `assessed_amount`: DecimalField
   - `remarks`: TextField

#### Key Relationships
- `Invoice.claim` -> `claims.Claim`, `Invoice.verified_by` -> `accounts.User`
- `Assessment.claim` -> `claims.Claim` (OneToOne)
- `AssessmentItem.assessment` -> `assessments.Assessment`

#### Service-Layer Functions (`assessments/services.py`)
- `recalculate_assessment(assessment)`: Automatically computes `gross_assessed_loss` as sum of line item `assessed_amount`s, calculates underinsurance, applies depreciation, deducts policy excess and salvage, and computes `net_assessed_loss = max(0, gross - dep - salvage - underinsurance - excess - other)`.
- `round_curr(val)`: Helper rounding monetary decimals to 2 places.

#### Web Views & URLs
- `claim_assessment_save`: `/claims/<int:pk>/assessment/save/` [name: `web_claim_assessment_save`]
- `claim_assessment_item_add`: `/claims/<int:pk>/assessment/item/add/` [name: `web_claim_assessment_item_add`]
- `claim_assessment_item_edit`: `/claims/<int:pk>/assessment/item/<int:item_id>/edit/` [name: `web_claim_assessment_item_edit`]
- `claim_assessment_item_delete`: `/claims/<int:pk>/assessment/item/<int:item_id>/delete/` [name: `web_claim_assessment_item_delete`]
- `claim_invoice_add`: `/claims/<int:pk>/invoices/add/` [name: `web_claim_invoice_add`]
- `claim_invoice_delete`: `/claims/<int:pk>/invoices/<int:inv_id>/delete/` [name: `web_claim_invoice_delete`]
- `claim_invoice_verify`: `/claims/<int:pk>/invoices/<int:inv_id>/verify/` [name: `web_claim_invoice_verify`]

#### DRF API Endpoints
- `GET/POST /api/assessments/` (`AssessmentViewSet`)
- `GET /api/claims/<pk>/assessment/` (nested on `ClaimViewSet`)

---

### 2.5 Reports App (`reports`)
*One-line Purpose:* Generates formal survey reports (Immediate Loss Advice - ILA, Interim Status Report - ISR, Final Survey Report - FSR) via WeasyPrint PDF compilation with Soteria branding, and logs immutable system audit events.

#### Models & Fields
1. **`AuditLog`**
   - `id`: BigAutoField
   - `user`: ForeignKey (`-> accounts.User`)
   - `claim`: ForeignKey (`-> claims.Claim`)
   - `action`: CharField
   - `model_name`: CharField
   - `object_id`: CharField
   - `description`: TextField
   - `timestamp`: DateTimeField
   - `ip_address`: GenericIPAddressField
2. **`ILA`** *(Immediate Loss Advice - Preliminary Report)*
   - `id`: BigAutoField
   - `claim`: ForeignKey (`-> claims.Claim`)
   - `report_number`: CharField
   - `report_date`: DateField
   - `status`: CharField (`DRAFT`, `SUBMITTED`, `APPROVED`, `QUERY`, `REVISED`)
   - `version_number`: PositiveIntegerField
   - `prepared_by`, `surveyor`: ForeignKey (`-> accounts.User`)
   - `submitted_at`: DateTimeField
   - `instruction_date`, `instruction_source`, `visit_date`, `visit_start_time`, `visit_end_time`: Date/Time fields
   - `inspection_location`, `person_contacted`, `contact_number`, `contact_email`, `policy_number`, `policy_type`, `policy_period`, `commodity`: CharFields
   - `sum_insured`, `policy_excess`, `estimated_loss`, `claimed_amount`, `budgetary_reserve`: DecimalField
   - `reason_for_delay`, `survey_and_inspection`, `extent_of_damage`, `cause_of_damage`, `salvage_prospect`, `policy_liability`, `remarks`: TextField
3. **`ISR`** *(Interim Status Report)*
   - `id`: BigAutoField
   - `claim`: ForeignKey (`-> claims.Claim`)
   - `report_number`: CharField, `report_date`: DateField, `status`: CharField, `version_number`: PositiveIntegerField
   - `prepared_by`: ForeignKey (`-> accounts.User`), `submitted_at`: DateTimeField
   - `introduction`, `occurrence_details`, `survey_details`, `extent_of_damage`, `cause_of_loss`, `initial_assessment`, `policy_liability`, `documents_received`, `documents_pending`, `remarks`, `recommendation`: TextField
4. **`FSR`** *(Final Survey Report)*
   - `id`: BigAutoField
   - `claim`: ForeignKey (`-> claims.Claim`)
   - `assessment`: ForeignKey (`-> assessments.Assessment`)
   - `report_number`: CharField, `report_date`: DateField, `status`: CharField, `version_number`: PositiveIntegerField
   - `prepared_by`: ForeignKey (`-> accounts.User`), `submitted_at`: DateTimeField, `approved_at`: DateTimeField
   - `introduction`, `occurrence_details`, `survey_details`, `extent_of_loss`, `cause_of_loss`, `adequacy_of_sum_insured`, `salvage_description`, `insured_claim_description`, `admissibility`, `policy_coverage`, `policy_exclusions`, `warranty_details`, `remarks`, `final_opinion`: TextField
   - `value_at_risk`, `sum_insured`, `underinsurance_percentage`, `salvage_amount`: DecimalField
   - `breach_of_warranty`: BooleanField

#### Key Relationships
- `AuditLog.claim` -> `claims.Claim`, `AuditLog.user` -> `accounts.User`
- `ILA.claim`, `ISR.claim`, `FSR.claim` -> `claims.Claim`
- `FSR.assessment` -> `assessments.Assessment`

#### Service-Layer Functions (`reports/services.py`)
- `generate_report_number(claim, report_type, version_number)`: Formats reference string e.g. `SOTERIA/2026/FSR/CLM-00001/v1`.
- `generate_report_pdf(report_instance)`: Renders HTML template with branding assets and compiles PDF binary via WeasyPrint.
- `save_report_pdf_as_document(report_instance, user)`: Renders PDF and attaches it directly as a permanent `ClaimDocument` record.
- `get_report_template(report_instance)`: Maps report instance to `ila_pdf.html`, `isr_pdf.html`, or `fsr_pdf.html`.
- `get_soteria_assets()`: Provides base64 encoded logos, letterhead, stamps, and signatures for self-contained PDF styling.
- `log_action(user, claim, action, model_name, object_id, description, request)`: Records an immutable audit log entry.
- `get_client_ip(request)`: Resolves real client IP address including reverse proxy headers.

#### Web Views & URLs
- `report_list`: `/reports/` [name: `web_report_list`]
- `claim_report_save`: `/claims/<int:pk>/report/<str:report_type>/save/` [name: `web_claim_report_save`]
- `claim_report_submit`: `/claims/<int:pk>/report/<str:report_type>/submit/` [name: `web_claim_report_submit`]
- `claim_report_preview`: `/claims/<int:pk>/report/<str:report_type>/preview/` [name: `web_claim_report_preview`]
- `claim_report_generate_pdf`: `/claims/<int:pk>/report/<str:report_type>/generate-pdf/` [name: `web_claim_report_generate_pdf`]

#### DRF API Endpoints
- `GET/POST /api/ila/`, `/api/ila/<pk>/generate-pdf/`, `/api/ila/<pk>/preview-pdf/`
- `GET/POST /api/isr/`, `/api/isr/<pk>/generate-pdf/`, `/api/isr/<pk>/preview-pdf/`
- `GET/POST /api/fsr/`, `/api/fsr/<pk>/generate-pdf/`, `/api/fsr/<pk>/preview-pdf/`
- Nested actions on `ClaimViewSet`: `/api/claims/<pk>/ila/`, `/api/claims/<pk>/isr/`, `/api/claims/<pk>/fsr/`

---

### 2.6 Documents App (`documents`)
*One-line Purpose:* Handles uploaded claim files, document type categorization, missing document Letter of Requirement (LOR) checklists, and authenticated media file serving.

#### Models & Fields
1. **`DocumentType`**
   - `id`: BigAutoField
   - `name`: CharField
   - `code`: CharField
   - `is_active`: BooleanField
   - `created_at`, `updated_at`: DateTimeField
2. **`ClaimDocument`**
   - `id`: BigAutoField
   - `claim`: ForeignKey (`-> claims.Claim`)
   - `document_type`: ForeignKey (`-> documents.DocumentType`)
   - `file`: FileField (Stored in `media/claim_documents/`)
   - `document_number`: CharField
   - `document_date`: DateField
   - `description`: TextField
   - `uploaded_by`: ForeignKey (`-> accounts.User`)
   - `uploaded_at`: DateTimeField
   - `verified`: BooleanField
   - `verified_by`: ForeignKey (`-> accounts.User`)
   - `verified_at`: DateTimeField
   - `remarks`: TextField
3. **`Requirement`** *(LOR Item)*
   - `id`: BigAutoField
   - `claim`: ForeignKey (`-> claims.Claim`)
   - `description`: TextField
   - `requested_from`: CharField
   - `requested_date`: DateField
   - `due_date`: DateField
   - `status`: CharField (`PENDING`, `RECEIVED`, `WAIVED`)
   - `received_date`: DateField
   - `related_document`: ForeignKey (`-> documents.ClaimDocument`)
   - `remarks`: TextField
   - `created_by`: ForeignKey (`-> accounts.User`)
   - `created_at`, `updated_at`: DateTimeField

#### Key Relationships
- `ClaimDocument.claim` -> `claims.Claim`, `ClaimDocument.document_type` -> `documents.DocumentType`
- `ClaimDocument.uploaded_by`, `ClaimDocument.verified_by` -> `accounts.User`
- `Requirement.claim` -> `claims.Claim`, `Requirement.related_document` -> `documents.ClaimDocument`

#### Service-Layer Functions (`documents/services.py`)
- `verify_claim_document(document, verified_by, remarks)`: Marks document as verified with timestamp and audit log.
- `update_requirement_status(requirement, new_status, related_document, remarks)`: Updates LOR item status, links document, and stamps receipt date.

#### Web Views & URLs
- `document_list`: `/documents/` [name: `web_document_list`]
- `secure_media_view`: `/media/<path:path>` [name: `secure_media`]
- `claim_document_upload`: `/claims/<int:pk>/documents/upload/` [name: `web_claim_document_upload`]
- `claim_document_verify`: `/claims/<int:pk>/documents/<int:doc_id>/verify/` [name: `web_claim_document_verify`]
- `claim_lor_add`: `/claims/<int:pk>/lor/add/` [name: `web_claim_lor_add`]
- `claim_lor_update_status`: `/claims/<int:pk>/lor/<int:req_id>/update-status/` [name: `web_claim_lor_update_status`]

#### DRF API Endpoints
- `GET/POST /api/documents/` (`ClaimDocumentViewSet`)
- `GET/POST /api/requirements/` (`RequirementViewSet`)
- Nested on `ClaimViewSet`: `/api/claims/<pk>/documents/`, `/api/claims/<pk>/requirements/`

---

### 2.7 Billing App (`billing`)
*One-line Purpose:* Models the surveying firm's own professional fee invoices issued to the Insurer for inspection/reporting services, complete with GST calculation, PDF bill generation, and payment settlement.

#### Models & Fields
1. **`ServiceInvoice`**
   - `id`: BigAutoField
   - `claim`: ForeignKey (`-> claims.Claim`)
   - `invoice_number`: CharField (Auto-generated sequential e.g. `SINV-00001`)
   - `invoice_date`: DateField
   - `due_date`: DateField
   - `status`: CharField (`DRAFT`, `SENT`, `PAID`, `CANCELLED`)
   - `sent_at`: DateTimeField
   - `paid_at`: DateTimeField
   - `payment_reference`: CharField
   - `subtotal`: DecimalField
   - `tax_percentage`: DecimalField (Default 18.00)
   - `tax_amount`: DecimalField
   - `total_amount`: DecimalField
   - `notes`: TextField (Printed on invoice)
   - `remarks`: TextField (Internal remarks)
   - `created_by`: ForeignKey (`-> accounts.User`)
   - `created_at`, `updated_at`: DateTimeField
2. **`ServiceInvoiceItem`**
   - `id`: BigAutoField
   - `invoice`: ForeignKey (`-> billing.ServiceInvoice`)
   - `description`: CharField
   - `quantity`: DecimalField
   - `rate`: DecimalField
   - `amount`: DecimalField (quantity * rate)
   - `created_at`, `updated_at`: DateTimeField

#### Key Relationships
- `ServiceInvoice.claim` -> `claims.Claim`
- `ServiceInvoice.created_by` -> `accounts.User`
- `ServiceInvoiceItem.invoice` -> `billing.ServiceInvoice`

#### Service-Layer Functions (`billing/services.py`)
- `recalculate_invoice(invoice)`: Recomputes subtotal from line items, calculates GST tax, and sets total.
- `add_invoice_item(invoice, description, quantity, rate)`: Adds item (enforces `DRAFT` status lock) and recalculates immediately.
- `update_invoice_item(item, description, quantity, rate)`: Updates item (enforces `DRAFT` status lock) and recalculates immediately.
- `delete_invoice_item(item)`: Deletes item (enforces `DRAFT` status lock) and recalculates immediately.
- `mark_invoice_sent(invoice)`: Transitions invoice from `DRAFT` to `SENT`, records timestamp, and locks all further line edits.
- `record_invoice_payment(invoice, payment_reference)`: Transitions invoice from `SENT` to `PAID` with payment reference and payment timestamp.
- `cancel_invoice(invoice, reason)`: Transitions invoice to `CANCELLED` and writes reason into remarks.
- `generate_invoice_pdf(invoice)`: Renders professional fee invoice PDF with firm details, GSTIN, line items, and bank details via WeasyPrint.

#### Web Views & URLs
- `invoice_list`: `/billing/` [name: `web_billing_invoice_list`]
- `claim_billing_create`: `/claims/<int:pk>/billing/create/` [name: `web_claim_billing_create`]
- `claim_billing_save`: `/claims/<int:pk>/billing/save/` [name: `web_claim_billing_save`]
- `claim_billing_item_add`: `/claims/<int:pk>/billing/item/add/` [name: `web_claim_billing_item_add`]
- `claim_billing_item_edit`: `/claims/<int:pk>/billing/item/<int:item_id>/edit/` [name: `web_claim_billing_item_edit`]
- `claim_billing_item_delete`: `/claims/<int:pk>/billing/item/<int:item_id>/delete/` [name: `web_claim_billing_item_delete`]
- `claim_billing_mark_sent`: `/claims/<int:pk>/billing/mark-sent/` [name: `web_claim_billing_mark_sent`]
- `claim_billing_record_payment`: `/claims/<int:pk>/billing/record-payment/` [name: `web_claim_billing_record_payment`]
- `claim_billing_cancel`: `/claims/<int:pk>/billing/cancel/` [name: `web_claim_billing_cancel`]
- `claim_billing_pdf`: `/claims/<int:pk>/billing/pdf/` [name: `web_claim_billing_pdf`]

#### DRF API Endpoints
- The billing workflow is implemented as an integrated web application inside the Surveyor Portal (`/billing/` and Claim Tab 8). DRF endpoints can be exposed on `billing/views.py` if mobile or external API clients require remote access.

---

## 3. How It Fits Together

### 3.1 Dual Web-UI + REST API Architecture & Shared Service Layer
The system provides two presentation channels over the same database:
1. **Web Portal UI (Server-Rendered HTML)**: Built with Django templates, vanilla modern CSS (`static/css/style.css`), and lightweight vanilla JavaScript for modals and tab navigation.
2. **RESTful JSON API**: Built with Django REST Framework (DRF) and documented automatically via OpenAPI 3.0 / Swagger UI (`/api/docs/`) using `drf-spectacular`.

**Single Source of Truth (No Logic Duplication):**
Neither Web views (`web_views.py`) nor DRF viewsets (`views.py`) perform business logic or state manipulation directly. Both layers act as lightweight transport controllers that validate input formats and call the unified functions in `services.py`:
- `claims.services.transition_claim_status()`
- `claims.services.assign_surveyor()`
- `assessments.services.recalculate_assessment()`
- `reports.services.generate_report_pdf()`
- `billing.services.recalculate_invoice()`
- `documents.services.verify_claim_document()`

If a transition rule or tax calculation changes, updating the service function automatically updates both the Web UI and the REST API simultaneously.

---

### 3.2 Role-Based Access Model (`ADMIN` vs `SURVEYOR`)
The application enforces strict separation between firm administrators and field surveyors across three distinct enforcement layers:

1. **Web Decorators (`claims/web_views.py`)**:
   - `@admin_required`: Restricts master data configuration, user management, claim creation, surveyor reassignment, invoice verification, and claim approval/closure to `role == 'ADMIN'` or `is_superuser`.
   - `@surveyor_required`: Restricts surveyor dashboard and inspection tools to authenticated surveyors or admins.
2. **DRF Permission Classes (`accounts/permissions.py`)**:
   - `IsAdminUserRole`: Checks `request.user.role == 'ADMIN'` for management API endpoints.
   - `IsSurveyorUserRole`: Grants field survey access.
   - `IsAssignedSurveyorOrAdmin`: Verifies that a surveyor making an update is explicitly assigned to that claim.
3. **Queryset & Object-Level Permission Filtering**:
   - `_get_claim_for_surveyor(request, pk)`: In web views, admins can access any claim, but a surveyor attempting to access a claim they are not assigned to triggers an immediate HTTP 403 `PermissionDenied`.
   - Dashboard filtering: Surveyor dashboards (`/dashboard/surveyor/`) filter `Claim.objects.filter(surveyassignment__surveyor=request.user)`.

---

### 3.3 Claim Status State Machine (`ALLOWED_TRANSITIONS`)
The lifecycle of an insurance claim follows an explicit directed state graph. The configuration dictionary lives in `claims/services.py` under **`ALLOWED_TRANSITIONS`**:

```python
ALLOWED_TRANSITIONS = {
    ClaimStatus.NEW: {ClaimStatus.ASSIGNED, ClaimStatus.INSPECTION_PENDING, ClaimStatus.ON_HOLD, ClaimStatus.CANCELLED},
    ClaimStatus.ASSIGNED: {ClaimStatus.INSPECTION_PENDING, ClaimStatus.INSPECTION_COMPLETED, ClaimStatus.DOCUMENT_COLLECTION, ClaimStatus.ON_HOLD, ClaimStatus.CANCELLED},
    ClaimStatus.INSPECTION_PENDING: {ClaimStatus.INSPECTION_COMPLETED, ClaimStatus.DOCUMENT_COLLECTION, ClaimStatus.ILA_PREPARED, ClaimStatus.ON_HOLD, ClaimStatus.CANCELLED},
    ClaimStatus.INSPECTION_COMPLETED: {ClaimStatus.DOCUMENT_COLLECTION, ClaimStatus.LOR_ISSUED, ClaimStatus.ASSESSMENT_IN_PROGRESS, ClaimStatus.ILA_PREPARED, ClaimStatus.ISR_PREPARED, ClaimStatus.FSR_PREPARED, ClaimStatus.ON_HOLD, ClaimStatus.CANCELLED},
    ClaimStatus.ILA_PREPARED: {ClaimStatus.DOCUMENT_COLLECTION, ClaimStatus.LOR_ISSUED, ClaimStatus.ASSESSMENT_IN_PROGRESS, ClaimStatus.ISR_PREPARED, ClaimStatus.FSR_PREPARED, ClaimStatus.REPORT_SUBMITTED, ClaimStatus.ON_HOLD, ClaimStatus.CANCELLED},
    ClaimStatus.LOR_ISSUED: {ClaimStatus.DOCUMENT_COLLECTION, ClaimStatus.ASSESSMENT_IN_PROGRESS, ClaimStatus.ISR_PREPARED, ClaimStatus.FSR_PREPARED, ClaimStatus.QUERY_RAISED, ClaimStatus.ON_HOLD, ClaimStatus.CANCELLED},
    ClaimStatus.DOCUMENT_COLLECTION: {ClaimStatus.LOR_ISSUED, ClaimStatus.ASSESSMENT_IN_PROGRESS, ClaimStatus.ISR_PREPARED, ClaimStatus.FSR_PREPARED, ClaimStatus.QUERY_RAISED, ClaimStatus.ON_HOLD, ClaimStatus.CANCELLED},
    ClaimStatus.ASSESSMENT_IN_PROGRESS: {ClaimStatus.DOCUMENT_COLLECTION, ClaimStatus.ISR_PREPARED, ClaimStatus.FSR_PREPARED, ClaimStatus.QUERY_RAISED, ClaimStatus.ON_HOLD, ClaimStatus.CANCELLED},
    ClaimStatus.ISR_PREPARED: {ClaimStatus.DOCUMENT_COLLECTION, ClaimStatus.ASSESSMENT_IN_PROGRESS, ClaimStatus.FSR_PREPARED, ClaimStatus.REPORT_SUBMITTED, ClaimStatus.QUERY_RAISED, ClaimStatus.ON_HOLD, ClaimStatus.CANCELLED},
    ClaimStatus.FSR_PREPARED: {ClaimStatus.REPORT_SUBMITTED, ClaimStatus.QUERY_RAISED, ClaimStatus.REVISION_REQUIRED, ClaimStatus.CLOSED, ClaimStatus.ON_HOLD, ClaimStatus.CANCELLED},
    ClaimStatus.REPORT_SUBMITTED: {ClaimStatus.DOCUMENT_COLLECTION, ClaimStatus.LOR_ISSUED, ClaimStatus.ASSESSMENT_IN_PROGRESS, ClaimStatus.ISR_PREPARED, ClaimStatus.FSR_PREPARED, ClaimStatus.QUERY_RAISED, ClaimStatus.REVISION_REQUIRED, ClaimStatus.RESUBMITTED, ClaimStatus.CLOSED, ClaimStatus.ON_HOLD, ClaimStatus.CANCELLED},
    ClaimStatus.QUERY_RAISED: {ClaimStatus.DOCUMENT_COLLECTION, ClaimStatus.ASSESSMENT_IN_PROGRESS, ClaimStatus.REPORT_SUBMITTED, ClaimStatus.RESUBMITTED, ClaimStatus.REVISION_REQUIRED, ClaimStatus.ON_HOLD, ClaimStatus.CANCELLED},
    ClaimStatus.REVISION_REQUIRED: {ClaimStatus.ASSESSMENT_IN_PROGRESS, ClaimStatus.FSR_PREPARED, ClaimStatus.REPORT_SUBMITTED, ClaimStatus.RESUBMITTED, ClaimStatus.ON_HOLD, ClaimStatus.CANCELLED},
    ClaimStatus.RESUBMITTED: {ClaimStatus.QUERY_RAISED, ClaimStatus.REVISION_REQUIRED, ClaimStatus.REPORT_SUBMITTED, ClaimStatus.CLOSED, ClaimStatus.ON_HOLD, ClaimStatus.CANCELLED},
    ClaimStatus.ON_HOLD: {ClaimStatus.NEW, ClaimStatus.ASSIGNED, ClaimStatus.INSPECTION_PENDING, ClaimStatus.INSPECTION_COMPLETED, ClaimStatus.DOCUMENT_COLLECTION, ClaimStatus.LOR_ISSUED, ClaimStatus.ILA_PREPARED, ClaimStatus.ISR_PREPARED, ClaimStatus.ASSESSMENT_IN_PROGRESS, ClaimStatus.FSR_PREPARED, ClaimStatus.REPORT_SUBMITTED, ClaimStatus.QUERY_RAISED, ClaimStatus.REVISION_REQUIRED, ClaimStatus.RESUBMITTED, ClaimStatus.CANCELLED},
    ClaimStatus.CLOSED: {ClaimStatus.QUERY_RAISED, ClaimStatus.REVISION_REQUIRED, ClaimStatus.ON_HOLD},
    ClaimStatus.CANCELLED: {ClaimStatus.NEW, ClaimStatus.ON_HOLD},
}
```

Whenever `transition_claim_status(claim, new_status, user, remarks)` is invoked:
1. It verifies that `new_status` is listed under `ALLOWED_TRANSITIONS[claim.status]`. If not, it raises a `ValidationError`.
2. It writes an immutable historical audit row into `ClaimStatusHistory` recording `old_status`, `new_status`, timestamp, and user.
3. It updates `claim.status` on the database.

---

### 3.4 PDF Generation Pipeline (WeasyPrint)
Reports and invoices are compiled into pixel-perfect PDF documents using **WeasyPrint**:

1. **Survey Reports (ILA, ISR, FSR)**:
   - Templates: `templates/reports/ila_pdf.html`, `isr_pdf.html`, `fsr_pdf.html`.
   - Visual Branding: `reports.services.get_soteria_assets()` injects high-resolution base64 encoded brand logos, letterhead styling, official stamps, and signature images directly into the HTML context.
   - Compilation: `weasyprint.HTML(string=html_string).write_pdf()` renders the output stream.
   - Persistence: `save_report_pdf_as_document()` saves the binary output directly into `media/claim_documents/` and registers a `ClaimDocument` record so that final reports are automatically archived in the claim's permanent document record.
2. **Billing Fee Invoices (Service Invoices)**:
   - Template: `billing/templates/billing/service_invoice_pdf.html`.
   - Layout: Standard Indian commercial tax invoice format with firm name, address, GSTIN, PAN, bank account / IFSC details, bill-to Insurer GSTIN, line-item fee breakdown, 18% GST breakdown, and amount in words.

---

### 3.5 File Upload Validation & Secure Media Serving
To prevent arbitrary file uploads and data leakage:

1. **Upload Validation**:
   - `documents/validators.py` and `surveys/validators.py` validate files before saving.
   - File size is restricted (maximum 10MB per file).
   - Extensions are strictly validated (`.pdf`, `.jpg`, `.jpeg`, `.png`, `.doc`, `.docx`).
2. **Protected Media Serving (`secure_media_view`)**:
   - `MEDIA_URL` (`/media/<path:path>`) is **NOT** exposed directly to public HTTP requests.
   - All requests are routed through `documents.views.secure_media_view`.
   - The view verifies authentication:
     - If the user is anonymous, redirects to login.
     - If the user is an `ADMIN` or superuser, access is granted.
     - If the user is a `SURVEYOR`, the view inspects whether the file belongs to an `InspectionPhoto`, `ClaimDocument`, or `Invoice` associated with a claim currently assigned to that surveyor.
     - Otherwise, raises an HTTP 403 Forbidden.
   - Authorized requests stream the binary file using Django's `FileResponse`.

---

## 4. Known Gaps & Not Yet Done

1. **Step 19 Deployment Configuration**:
   - Gunicorn/Uvicorn systemd service definitions, Nginx reverse proxy configuration, and automated SSL/TLS certificates via Let's Encrypt / Certbot have been designed but not yet deployed to a live production server.
2. **Production PostgreSQL Migration**:
   - `config/settings/prod.py` is configured with PostgreSQL drivers and settings, but the local environment runs on SQLite (`db.sqlite3`). A PostgreSQL database needs to be provisioned and `python manage.py migrate` executed on the production host.
3. **Firm Profile Configuration**:
   - `FIRM_NAME`, `FIRM_ADDRESS`, and `FIRM_GSTIN` in `config/settings/base.py` currently contain Soteria defaults:
     ```python
     FIRM_NAME = 'SOTERIA Insurance Surveyors & Loss Assessors Pvt. Ltd.'
     FIRM_ADDRESS = 'Z3215, 3rd floor, Akshar Business Park, Sector 25 Vashi-Thurbe, Navi Mumbai, Maharashtra-400703'
     FIRM_GSTIN = '27AAACS0000A1Z5'
     ```
     These should be populated from environment variables (`.env`) for other surveying firms.
4. **WeasyPrint System-Level Dependencies**:
   - WeasyPrint requires native C-libraries installed on the operating system: Pango, Cairo, GDK-PixBuf, and GLib. On Windows, this requires the GTK3 runtime; on Linux (Ubuntu/Debian), it requires `libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libpango1.0-dev`.
5. **Billing App DRF Endpoints**:
   - The billing app is fully integrated with the server-rendered web portal (`/billing/` and Claim Tab 8). DRF serializers and API ViewSets for `ServiceInvoice` have been left as a future expansion if mobile applications need to interact with fee invoices.

---

## 5. Summary Counts

| Metric | Count |
| :--- | :--- |
| **Installed Custom Apps** | **7** (`accounts`, `claims`, `surveys`, `assessments`, `reports`, `documents`, `billing`) |
| **Database Models** | **28** |
| **Web Portal Endpoints / Views** | **58** |
| **REST API Endpoints** | **103** |
| **Automated Test Cases** | **169** (All passing, 0 failures, 0 errors) |
