from django.contrib import admin
from .models import Insurer, Insured, Policy, Claim, SurveyAssignment, ClaimStatusHistory
from surveys.models import (
    FireClaimDetails,
    EngineeringClaimDetails,
    MarineClaimDetails,
    PropertyClaimDetails,
)


class SurveyAssignmentInline(admin.TabularInline):
    model = SurveyAssignment
    extra = 0
    fields = ('surveyor', 'assigned_by', 'priority', 'status', 'due_date', 'remarks')


class ClaimStatusHistoryInline(admin.TabularInline):
    model = ClaimStatusHistory
    extra = 0
    readonly_fields = ('old_status', 'new_status', 'changed_by', 'changed_at', 'remarks')
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class FireClaimDetailsInline(admin.StackedInline):
    model = FireClaimDetails
    can_delete = False
    extra = 0


class EngineeringClaimDetailsInline(admin.StackedInline):
    model = EngineeringClaimDetails
    can_delete = False
    extra = 0


class MarineClaimDetailsInline(admin.StackedInline):
    model = MarineClaimDetails
    can_delete = False
    extra = 0


class PropertyClaimDetailsInline(admin.StackedInline):
    model = PropertyClaimDetails
    can_delete = False
    extra = 0


@admin.register(Insurer)
class InsurerAdmin(admin.ModelAdmin):
    list_display = ('company_name', 'branch_name', 'contact_person', 'phone', 'email', 'city', 'state', 'is_active')
    list_filter = ('is_active', 'state', 'city')
    search_fields = ('company_name', 'branch_name', 'contact_person', 'phone', 'email')
    ordering = ('company_name', 'branch_name')


@admin.register(Insured)
class InsuredAdmin(admin.ModelAdmin):
    list_display = ('name', 'company_name', 'contact_person', 'phone', 'email', 'city', 'state', 'is_active')
    list_filter = ('is_active', 'state', 'city')
    search_fields = ('name', 'company_name', 'contact_person', 'phone', 'email', 'gstin')
    ordering = ('name',)


@admin.register(Policy)
class PolicyAdmin(admin.ModelAdmin):
    list_display = ('policy_number', 'insurer', 'policy_type', 'sum_insured', 'excess', 'start_datetime', 'end_datetime')
    list_filter = ('policy_type', 'insurer')
    search_fields = ('policy_number', 'commodity', 'insurer__company_name')
    ordering = ('-created_at',)


@admin.register(Claim)
class ClaimAdmin(admin.ModelAdmin):
    list_display = (
        'claim_number',
        'report_number',
        'survey_type',
        'insurer',
        'insured',
        'date_of_loss',
        'claimed_amount',
        'priority',
        'status',
        'created_at',
    )
    list_filter = ('status', 'priority', 'survey_type', 'insurer', 'date_of_loss')
    search_fields = ('claim_number', 'report_number', 'insured__name', 'insurer__company_name', 'loss_location')
    readonly_fields = ('claim_number', 'created_at', 'updated_at')
    ordering = ('-created_at',)

    def get_inlines(self, request, obj=None):
        inlines = [SurveyAssignmentInline, ClaimStatusHistoryInline]
        if obj and obj.survey_type:
            code = obj.survey_type.code
            if code == 'FIRE':
                inlines.append(FireClaimDetailsInline)
            elif code == 'ENG':
                inlines.append(EngineeringClaimDetailsInline)
            elif code == 'MARINE':
                inlines.append(MarineClaimDetailsInline)
            elif code == 'PROPERTY':
                inlines.append(PropertyClaimDetailsInline)
        return inlines


@admin.register(SurveyAssignment)
class SurveyAssignmentAdmin(admin.ModelAdmin):
    list_display = ('claim', 'surveyor', 'assigned_by', 'priority', 'status', 'due_date', 'assigned_at')
    list_filter = ('status', 'priority', 'due_date', 'surveyor')
    search_fields = ('claim__claim_number', 'surveyor__username', 'surveyor__first_name', 'surveyor__last_name')
    readonly_fields = ('assigned_at',)
    ordering = ('-assigned_at',)


@admin.register(ClaimStatusHistory)
class ClaimStatusHistoryAdmin(admin.ModelAdmin):
    list_display = ('claim', 'old_status', 'new_status', 'changed_by', 'changed_at')
    list_filter = ('old_status', 'new_status', 'changed_at')
    search_fields = ('claim__claim_number', 'changed_by__username', 'remarks')
    readonly_fields = ('claim', 'old_status', 'new_status', 'changed_by', 'changed_at', 'remarks')
    ordering = ('-changed_at',)

    def has_add_permission(self, request):
        return False
