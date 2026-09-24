from django.urls import path
from . import web_views

urlpatterns = [
    # Top-level invoices list
    path('billing/', web_views.invoice_list, name='web_billing_invoice_list'),

    # Claim billing tab actions
    path('claims/<int:pk>/billing/create/', web_views.claim_billing_create, name='web_claim_billing_create'),
    path('claims/<int:pk>/billing/save/', web_views.claim_billing_save, name='web_claim_billing_save'),
    path('claims/<int:pk>/billing/item/add/', web_views.claim_billing_item_add, name='web_claim_billing_item_add'),
    path('claims/<int:pk>/billing/item/<int:item_id>/edit/', web_views.claim_billing_item_edit, name='web_claim_billing_item_edit'),
    path('claims/<int:pk>/billing/item/<int:item_id>/delete/', web_views.claim_billing_item_delete, name='web_claim_billing_item_delete'),
    path('claims/<int:pk>/billing/mark-sent/', web_views.claim_billing_mark_sent, name='web_claim_billing_mark_sent'),
    path('claims/<int:pk>/billing/record-payment/', web_views.claim_billing_record_payment, name='web_claim_billing_record_payment'),
    path('claims/<int:pk>/billing/cancel/', web_views.claim_billing_cancel, name='web_claim_billing_cancel'),
    path('claims/<int:pk>/billing/pdf/', web_views.claim_billing_pdf, name='web_claim_billing_pdf'),
]
