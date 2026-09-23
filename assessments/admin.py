from django.contrib import admin
from .models import Invoice, Assessment, AssessmentItem
from .services import recalculate_assessment


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = (
        'claim',
        'invoice_number',
        'vendor_name',
        'invoice_date',
        'amount',
        'tax_amount',
        'total_amount',
        'verified',
        'verified_by',
    )
    list_filter = ('verified', 'invoice_date')
    search_fields = ('invoice_number', 'vendor_name', 'claim__claim_number', 'description')
    ordering = ('-invoice_date', '-created_at')


class AssessmentItemInline(admin.TabularInline):
    model = AssessmentItem
    extra = 1
    readonly_fields = ('assessed_amount',)
    fields = (
        'item_code',
        'description',
        'specification',
        'category',
        'quantity',
        'rate',
        'claimed_amount',
        'assessed_amount',
    )


@admin.register(Assessment)
class AssessmentAdmin(admin.ModelAdmin):
    list_display = (
        'claim',
        'gross_assessed_loss',
        'underinsurance_percentage',
        'underinsurance_amount',
        'adjusted_loss',
        'policy_excess',
        'net_assessed_loss',
        'created_by',
        'updated_at',
    )
    readonly_fields = (
        'gross_assessed_loss',
        'underinsurance_amount',
        'adjusted_loss',
        'net_assessed_loss',
        'created_at',
        'updated_at',
    )
    search_fields = ('claim__claim_number', 'assessment_remarks', 'created_by__username')
    inlines = [AssessmentItemInline]
    ordering = ('-created_at',)
    actions = ['trigger_recalculation']

    @admin.action(description="Recalculate financial figures for selected assessments")
    def trigger_recalculation(self, request, queryset):
        for assessment in queryset:
            recalculate_assessment(assessment)
        self.message_user(request, f"Successfully recalculated {queryset.count()} assessment(s).")

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        recalculate_assessment(form.instance)
