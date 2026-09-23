from django.contrib import admin
from .models import DocumentType, ClaimDocument, Requirement


@admin.register(DocumentType)
class DocumentTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'is_active', 'created_at', 'updated_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'code')
    ordering = ('name',)


@admin.register(ClaimDocument)
class ClaimDocumentAdmin(admin.ModelAdmin):
    list_display = (
        'claim',
        'document_type',
        'document_number',
        'document_date',
        'uploaded_by',
        'uploaded_at',
        'verified',
        'verified_by',
    )
    list_filter = ('claim', 'document_type', 'verified', 'uploaded_at')
    search_fields = ('description', 'document_number', 'claim__claim_number', 'remarks')
    ordering = ('-uploaded_at',)


@admin.register(Requirement)
class RequirementAdmin(admin.ModelAdmin):
    list_display = (
        'claim',
        'description',
        'requested_from',
        'requested_date',
        'due_date',
        'status',
        'received_date',
        'related_document',
    )
    list_filter = ('claim', 'status', 'requested_from', 'requested_date')
    search_fields = ('description', 'remarks', 'claim__claim_number')
    ordering = ('-requested_date', '-created_at',)
