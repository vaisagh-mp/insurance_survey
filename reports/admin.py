from django.contrib import admin
from .models import AuditLog, ILA, ISR, FSR


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'action', 'user', 'model_name', 'object_id', 'ip_address')
    list_filter = ('action', 'model_name', 'timestamp')
    search_fields = ('action', 'model_name', 'object_id', 'description', 'user__username', 'ip_address')
    readonly_fields = ('timestamp', 'action', 'user', 'model_name', 'object_id', 'description', 'ip_address')
    ordering = ('-timestamp',)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ILA)
class ILAAdmin(admin.ModelAdmin):
    list_display = (
        'report_number',
        'claim',
        'report_date',
        'status',
        'version_number',
        'estimated_loss',
        'claimed_amount',
        'prepared_by',
    )
    list_filter = ('status', 'report_date', 'surveyor')
    search_fields = ('report_number', 'claim__claim_number', 'person_contacted', 'policy_number')
    ordering = ('-report_date', '-created_at')


@admin.register(ISR)
class ISRAdmin(admin.ModelAdmin):
    list_display = (
        'report_number',
        'claim',
        'report_date',
        'status',
        'version_number',
        'prepared_by',
    )
    list_filter = ('status', 'report_date')
    search_fields = ('report_number', 'claim__claim_number', 'occurrence_details')
    ordering = ('-report_date', '-created_at')


@admin.register(FSR)
class FSRAdmin(admin.ModelAdmin):
    list_display = (
        'report_number',
        'claim',
        'report_date',
        'status',
        'version_number',
        'sum_insured',
        'assessment',
        'prepared_by',
        'approved_at',
    )
    list_filter = ('status', 'report_date', 'breach_of_warranty')
    search_fields = ('report_number', 'claim__claim_number', 'admissibility', 'final_opinion')
    ordering = ('-report_date', '-created_at')
