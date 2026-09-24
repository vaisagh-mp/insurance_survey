from django.urls import path
from . import web_views

urlpatterns = [
    # Auth
    path('login/', web_views.web_login, name='web_login'),
    path('logout/', web_views.web_logout, name='web_logout'),

    # Dashboards
    path('dashboard/admin/', web_views.admin_dashboard, name='admin_dashboard'),
    path('dashboard/surveyor/', web_views.surveyor_dashboard, name='surveyor_dashboard'),

    # Claims
    path('claims/', web_views.claim_list, name='web_claim_list'),
    path('claims/create/', web_views.claim_create, name='web_claim_create'),
    path('claims/<int:pk>/', web_views.claim_detail, name='web_claim_detail'),
    path('claims/<int:pk>/assign/', web_views.claim_assign_surveyor, name='web_claim_assign_surveyor'),

    # Claim Tab Actions (Surveyor Interactive Submissions)
    path('claims/<int:pk>/inspection/save/', web_views.claim_inspection_save, name='web_claim_inspection_save'),
    path('claims/<int:pk>/lor/add/', web_views.claim_lor_add, name='web_claim_lor_add'),
    path('claims/<int:pk>/lor/<int:req_id>/update-status/', web_views.claim_lor_update_status, name='web_claim_lor_update_status'),
    path('claims/<int:pk>/documents/<int:doc_id>/verify/', web_views.claim_document_verify, name='web_claim_document_verify'),
    path('claims/<int:pk>/documents/upload/', web_views.claim_document_upload, name='web_claim_document_upload'),
    path('claims/<int:pk>/invoices/add/', web_views.claim_invoice_add, name='web_claim_invoice_add'),
    path('claims/<int:pk>/invoices/<int:inv_id>/delete/', web_views.claim_invoice_delete, name='web_claim_invoice_delete'),
    path('claims/<int:pk>/invoices/<int:inv_id>/verify/', web_views.claim_invoice_verify, name='web_claim_invoice_verify'),
    path('claims/<int:pk>/assessment/save/', web_views.claim_assessment_save, name='web_claim_assessment_save'),
    path('claims/<int:pk>/assessment/item/add/', web_views.claim_assessment_item_add, name='web_claim_assessment_item_add'),
    path('claims/<int:pk>/assessment/item/<int:item_id>/delete/', web_views.claim_assessment_item_delete, name='web_claim_assessment_item_delete'),
    path('claims/<int:pk>/assessment/item/<int:item_id>/edit/', web_views.claim_assessment_item_edit, name='web_claim_assessment_item_edit'),
    path('claims/<int:pk>/report/<str:report_type>/save/', web_views.claim_report_save, name='web_claim_report_save'),
    path('claims/<int:pk>/report/<str:report_type>/submit/', web_views.claim_report_submit, name='web_claim_report_submit'),
    path('claims/<int:pk>/report/<str:report_type>/preview/', web_views.claim_report_preview, name='web_claim_report_preview'),
    path('claims/<int:pk>/report/<str:report_type>/generate-pdf/', web_views.claim_report_generate_pdf, name='web_claim_report_generate_pdf'),
    path('claims/<int:pk>/approve-and-close/', web_views.claim_approve_and_close, name='web_claim_approve_and_close'),

    # Surveyors
    path('surveyors/', web_views.surveyor_list, name='web_surveyor_list'),
    path('surveyors/add/', web_views.surveyor_add, name='web_surveyor_add'),
    path('surveyors/<int:pk>/edit/', web_views.surveyor_edit, name='web_surveyor_edit'),
    path('surveyors/workload/', web_views.surveyor_workload, name='web_surveyor_workload'),

    # Insurers
    path('insurers/', web_views.insurer_list, name='web_insurer_list'),
    path('insurers/add/', web_views.insurer_add, name='web_insurer_add'),
    path('insurers/<int:pk>/edit/', web_views.insurer_edit, name='web_insurer_edit'),

    # Insured
    path('insured/', web_views.insured_list, name='web_insured_list'),
    path('insured/add/', web_views.insured_add, name='web_insured_add'),
    path('insured/<int:pk>/edit/', web_views.insured_edit, name='web_insured_edit'),

    # Policies
    path('policies/', web_views.policy_list, name='web_policy_list'),
    path('policies/add/', web_views.policy_add, name='web_policy_add'),
    path('policies/<int:pk>/edit/', web_views.policy_edit, name='web_policy_edit'),

    # Documents & Reports
    path('documents/', web_views.document_list, name='web_document_list'),
    path('reports/', web_views.report_list, name='web_report_list'),

    # Master Data
    path('master/survey-types/', web_views.master_survey_types, name='web_master_survey_types'),
    path('master/document-types/', web_views.master_document_types, name='web_master_document_types'),
    path('master/claim-statuses/', web_views.master_claim_statuses, name='web_master_claim_statuses'),

    # Users & Audit
    path('users/', web_views.user_list, name='web_user_list'),
    path('audit/', web_views.audit_list, name='web_audit_list'),
]
