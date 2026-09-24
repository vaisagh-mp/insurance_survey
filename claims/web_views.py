from functools import wraps
from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator
from django.core.exceptions import PermissionDenied, ValidationError
from django.contrib import messages
from django.contrib.auth import login as auth_login, logout as auth_logout, get_user_model
from django.db.models import Count, Q
from django.utils import timezone

from accounts.forms import WebLoginForm, SurveyorCreateForm, SurveyorUpdateForm
from accounts.models import SurveyorProfile
from claims.models import Claim, ClaimStatus, Insurer, Insured, Policy, SurveyAssignment
from claims.forms import (
    InsurerForm, InsuredForm, PolicyForm, ClaimCreateForm,
    FireClaimDetailsForm, EngineeringClaimDetailsForm, MarineClaimDetailsForm, PropertyClaimDetailsForm
)
from surveys.models import SurveyType, Inspection, InspectionPhoto, InspectionObservation
from surveys.forms import InspectionForm
from documents.models import DocumentType, ClaimDocument, Requirement
from documents.forms import RequirementForm, ClaimDocumentForm
from assessments.models import Assessment, AssessmentItem, Invoice
from assessments.forms import AssessmentFinancialForm, AssessmentItemForm, InvoiceForm
from assessments.services import recalculate_assessment
from reports.models import AuditLog, ILA, ISR, FSR, ReportStatus
from reports.forms import ILAForm, ISRForm, FSRForm
from reports.services import generate_report_pdf, save_report_pdf_as_document, generate_report_number
from claims.services import submit_report, transition_claim_status, assign_surveyor, reassign_surveyor, close_claim
from django.db import transaction

User = get_user_model()


def admin_required(view_func):
    """Decorator ensuring that only authenticated users with ADMIN role can access the view."""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f"/login/?next={request.path}")
        if request.user.role != User.Role.ADMIN and not request.user.is_superuser:
            raise PermissionDenied("Administrator privileges are required to access this section.")
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def surveyor_required(view_func):
    """Decorator ensuring that only authenticated users with SURVEYOR role (or superusers) can access."""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f"/login/?next={request.path}")
        if request.user.role != User.Role.SURVEYOR and not request.user.is_superuser:
            raise PermissionDenied("Surveyor privileges are required to access this section.")
        return view_func(request, *args, **kwargs)
    return _wrapped_view


# --- Authentication Views ---

def web_login(request):
    if request.user.is_authenticated:
        if request.user.role == User.Role.ADMIN or request.user.is_superuser:
            return redirect('/dashboard/admin/')
        elif request.user.role == User.Role.SURVEYOR:
            return redirect('/dashboard/surveyor/')
        messages.warning(request, "You are logged in, but your role does not have an active portal.")

    if request.method == 'POST':
        form = WebLoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            auth_login(request, user)
            messages.success(request, f"Welcome back, {user.get_full_name() or user.username}!")
            default_next = '/dashboard/admin/' if user.role == User.Role.ADMIN or user.is_superuser else '/dashboard/surveyor/'
            next_url = request.GET.get('next') or request.POST.get('next') or default_next
            return redirect(next_url)
        else:
            messages.error(request, "Invalid username or password.")
    else:
        form = WebLoginForm()

    return render(request, 'login.html', {'form': form})


def web_logout(request):
    auth_logout(request)
    messages.info(request, "You have been logged out.")
    return redirect('/login/')


# --- Surveyor Dashboard ---

@surveyor_required
def surveyor_dashboard(request):
    """
    Surveyor Dashboard at /dashboard/surveyor/ showing tiles with EXACT status mapping,
    all scoped to claims where request.user is the current_surveyor:
    - My Assigned Claims: total count in scoped queryset
    - Today's Inspections: Inspection.objects.filter(surveyor=request.user, inspection_date=today).count()
    - Pending ILA: status=INSPECTION_COMPLETED
    - Pending LOR: status=ILA_PREPARED
    - Pending Documents: status=LOR_ISSUED
    - Pending Assessment: status=DOCUMENT_COLLECTION
    - Pending ISR: status=ASSESSMENT_IN_PROGRESS
    - Pending FSR: status=ISR_PREPARED
    - Completed: status in [REPORT_SUBMITTED, CLOSED]
    Below, "My Claims" table: Claim No., Type, Status.
    """
    from django.utils import timezone
    from surveys.models import Inspection
    from accounts.permissions import filter_claim_scoped_queryset

    today = timezone.localdate()
    scoped_claims = filter_claim_scoped_queryset(Claim.objects.all(), request.user, claim_lookup='self')

    my_assigned_count = scoped_claims.count()
    todays_inspections = Inspection.objects.filter(surveyor=request.user, inspection_date=today).count()
    pending_ila = scoped_claims.filter(status=ClaimStatus.INSPECTION_COMPLETED).count()
    pending_lor = scoped_claims.filter(status=ClaimStatus.ILA_PREPARED).count()
    pending_documents = scoped_claims.filter(status=ClaimStatus.LOR_ISSUED).count()
    pending_assessment = scoped_claims.filter(status=ClaimStatus.DOCUMENT_COLLECTION).count()
    pending_isr = scoped_claims.filter(status=ClaimStatus.ASSESSMENT_IN_PROGRESS).count()
    pending_fsr = scoped_claims.filter(status=ClaimStatus.ISR_PREPARED).count()
    completed_claims = scoped_claims.filter(
        status__in=[ClaimStatus.REPORT_SUBMITTED, ClaimStatus.CLOSED]
    ).count()

    tiles = [
        {'title': 'My Assigned Claims', 'count': my_assigned_count, 'url': '/claims/', 'color': 'primary'},
        {'title': "Today's Inspections", 'count': todays_inspections, 'url': '/claims/', 'color': 'warning'},
        {'title': 'Pending ILA', 'count': pending_ila, 'url': '/claims/?status=INSPECTION_COMPLETED', 'color': 'secondary'},
        {'title': 'Pending LOR', 'count': pending_lor, 'url': '/claims/?status=ILA_PREPARED', 'color': 'secondary'},
        {'title': 'Pending Documents', 'count': pending_documents, 'url': '/claims/?status=LOR_ISSUED', 'color': 'warning'},
        {'title': 'Pending Assessment', 'count': pending_assessment, 'url': '/claims/?status=DOCUMENT_COLLECTION', 'color': 'warning'},
        {'title': 'Pending ISR', 'count': pending_isr, 'url': '/claims/?status=ASSESSMENT_IN_PROGRESS', 'color': 'secondary'},
        {'title': 'Pending FSR', 'count': pending_fsr, 'url': '/claims/?status=ISR_PREPARED', 'color': 'secondary'},
        {'title': 'Completed', 'count': completed_claims, 'url': '/claims/?filter=completed', 'color': 'success'},
    ]

    my_claims = scoped_claims.select_related('survey_type', 'insurer', 'insured').order_by('-created_at')[:25]

    context = {
        'tiles': tiles,
        'my_claims': my_claims,
    }
    return render(request, 'dashboard/surveyor_dashboard.html', context)


# --- Admin Dashboard ---

@admin_required
def admin_dashboard(request):
    """
    Admin Dashboard at /dashboard/admin/ with exact status-mapped tiles:
    1. Total Claims = Claim.objects.count()
    2. New = status=NEW
    3. Unassigned = claims with no active SurveyAssignment (exclude status=REASSIGNED), regardless of Claim.status
    4. Assigned = status=ASSIGNED
    5. Inspection Pending = status=INSPECTION_PENDING
    6. ILA Pending = status=INSPECTION_COMPLETED
    7. LOR Pending = status=ILA_PREPARED
    8. Assessment Pending = status in [LOR_ISSUED, DOCUMENT_COLLECTION]
    9. ISR Pending = status=ASSESSMENT_IN_PROGRESS
    10. FSR Pending = status=ISR_PREPARED
    11. Submitted = status=REPORT_SUBMITTED
    12. Closed = status=CLOSED
    """
    total_claims = Claim.objects.count()
    new_claims = Claim.objects.filter(status=ClaimStatus.NEW).count()
    
    # Unassigned: claims with no active SurveyAssignment (excluding REASSIGNED)
    active_assignment_claim_ids = SurveyAssignment.objects.exclude(
        status=SurveyAssignment.Status.REASSIGNED
    ).values_list('claim_id', flat=True).distinct()
    unassigned_claims = Claim.objects.exclude(id__in=active_assignment_claim_ids).count()

    assigned_claims = Claim.objects.filter(status=ClaimStatus.ASSIGNED).count()
    inspection_pending = Claim.objects.filter(status=ClaimStatus.INSPECTION_PENDING).count()
    ila_pending = Claim.objects.filter(status=ClaimStatus.INSPECTION_COMPLETED).count()
    lor_pending = Claim.objects.filter(status=ClaimStatus.ILA_PREPARED).count()
    assessment_pending = Claim.objects.filter(
        status__in=[ClaimStatus.LOR_ISSUED, ClaimStatus.DOCUMENT_COLLECTION]
    ).count()
    isr_pending = Claim.objects.filter(status=ClaimStatus.ASSESSMENT_IN_PROGRESS).count()
    fsr_pending = Claim.objects.filter(status=ClaimStatus.ISR_PREPARED).count()
    submitted_claims = Claim.objects.filter(status=ClaimStatus.REPORT_SUBMITTED).count()
    closed_claims = Claim.objects.filter(status=ClaimStatus.CLOSED).count()

    tiles = [
        {'title': 'Total Claims', 'count': total_claims, 'url': '/claims/', 'color': 'primary'},
        {'title': 'New', 'count': new_claims, 'url': '/claims/?status=NEW', 'color': 'info'},
        {'title': 'Unassigned', 'count': unassigned_claims, 'url': '/claims/?filter=unassigned', 'color': 'warning'},
        {'title': 'Assigned', 'count': assigned_claims, 'url': '/claims/?status=ASSIGNED', 'color': 'primary'},
        {'title': 'Inspection Pending', 'count': inspection_pending, 'url': '/claims/?status=INSPECTION_PENDING', 'color': 'warning'},
        {'title': 'ILA Pending', 'count': ila_pending, 'url': '/claims/?status=INSPECTION_COMPLETED', 'color': 'secondary'},
        {'title': 'LOR Pending', 'count': lor_pending, 'url': '/claims/?status=ILA_PREPARED', 'color': 'secondary'},
        {'title': 'Assessment Pending', 'count': assessment_pending, 'url': '/claims/?filter=assessment_pending', 'color': 'warning'},
        {'title': 'ISR Pending', 'count': isr_pending, 'url': '/claims/?status=ASSESSMENT_IN_PROGRESS', 'color': 'secondary'},
        {'title': 'FSR Pending', 'count': fsr_pending, 'url': '/claims/?status=ISR_PREPARED', 'color': 'secondary'},
        {'title': 'Submitted', 'count': submitted_claims, 'url': '/claims/?status=REPORT_SUBMITTED', 'color': 'success'},
        {'title': 'Closed', 'count': closed_claims, 'url': '/claims/?status=CLOSED', 'color': 'dark'},
    ]

    recent_claims = Claim.objects.select_related(
        'survey_type', 'insurer', 'insured'
    ).prefetch_related('assignments__surveyor').order_by('-created_at')[:10]

    context = {
        'tiles': tiles,
        'recent_claims': recent_claims,
    }
    return render(request, 'dashboard/admin_dashboard.html', context)


# --- Claims Views ---

def claim_list(request):
    """
    Claims list view:
    - Scoped for Surveyors: only assigned claims.
    - Unrestricted for Admins/superusers.
    Columns: Claim No., Type, Insurer, Insured, Surveyor, Status, Created.
    Filterable by status, survey_type, and preset filters (unassigned, in_progress, completed).
    Paginated.
    """
    if not request.user.is_authenticated:
        return redirect(f"/login/?next={request.path}")

    from accounts.permissions import filter_claim_scoped_queryset

    queryset = Claim.objects.select_related(
        'survey_type', 'insurer', 'insured'
    ).prefetch_related('assignments__surveyor').order_by('-created_at')

    # Apply role scoping
    queryset = filter_claim_scoped_queryset(queryset, request.user, claim_lookup='self')

    status_filter = request.GET.get('status')
    survey_type_filter = request.GET.get('survey_type')
    custom_filter = request.GET.get('filter')

    if status_filter:
        queryset = queryset.filter(status=status_filter)

    if survey_type_filter:
        queryset = queryset.filter(survey_type_id=survey_type_filter)

    if custom_filter == 'unassigned':
        active_assignment_claim_ids = SurveyAssignment.objects.exclude(
            status=SurveyAssignment.Status.REASSIGNED
        ).values_list('claim_id', flat=True).distinct()
        queryset = queryset.exclude(id__in=active_assignment_claim_ids)
    elif custom_filter == 'in_progress':
        # "In Progress" filter = status NOT IN [NEW, CLOSED, CANCELLED] (submitted-but-not-closed is active work)
        queryset = queryset.exclude(
            status__in=[ClaimStatus.NEW, ClaimStatus.CLOSED, ClaimStatus.CANCELLED]
        )
    elif custom_filter == 'assessment_pending':
        queryset = queryset.filter(status__in=[ClaimStatus.LOR_ISSUED, ClaimStatus.DOCUMENT_COLLECTION])
    elif custom_filter == 'completed':
        queryset = queryset.filter(status__in=[ClaimStatus.REPORT_SUBMITTED, ClaimStatus.CLOSED])

    paginator = Paginator(queryset, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    survey_types = SurveyType.objects.filter(is_active=True)
    claim_statuses = ClaimStatus.choices

    context = {
        'page_obj': page_obj,
        'survey_types': survey_types,
        'claim_statuses': claim_statuses,
        'current_status': status_filter or '',
        'current_survey_type': survey_type_filter or '',
        'current_filter': custom_filter or '',
        'total_count': paginator.count,
    }
    return render(request, 'claims/claim_list.html', context)


def claim_detail(request, pk):
    """
    Central claim detail workspace at /claims/<id>/ shared by both ADMIN and SURVEYOR:
    - If SURVEYOR: checks that claim has an active SurveyAssignment for request.user.
      If not, raises PermissionDenied (HTTP 403).
    - If ADMIN: unrestricted access.
    13 tabs supported via '?tab=<slug>':
      1. Overview (summary, current_surveyor property, details)
      2. Assignment (assignment history, active surveyor)
      3. Policy (policy info, sum insured, excess, remarks)
      4. Inspection (inspection appointments, details, observations)
      5. ILA (Immediate Loss Advice report details & PDF link)
      6. LOR (List of Requirements / documents requested)
      7. Documents (Claim documents, verification status, download)
      8. Photos (Inspection photos by category)
      9. Invoices (Repair/loss invoices and verification)
      10. Assessment (Assessment figures, items, underinsurance, net loss)
      11. ISR (Initial Survey Report details & PDF link)
      12. FSR (Final Survey Report details, linked assessment & PDF link)
      13. Activity (Unified chronological timeline of ClaimStatusHistory + AuditLog with claim=claim)
    """
    if not request.user.is_authenticated:
        return redirect(f"/login/?next={request.path}")

    claim = get_object_or_404(
        Claim.objects.select_related('survey_type', 'insurer', 'insured', 'policy', 'created_by'),
        pk=pk
    )

    # Permission check for Surveyor: must have an active (non-reassigned) assignment to this claim
    if request.user.role == User.Role.SURVEYOR and not request.user.is_superuser:
        is_assigned = claim.assignments.filter(surveyor=request.user).exclude(
            status=SurveyAssignment.Status.REASSIGNED
        ).exists()
        if not is_assigned:
            raise PermissionDenied("You are not assigned to this claim.")

    # Valid tabs definition
    valid_tabs = [
        'overview', 'assignment', 'policy', 'inspection', 'ila',
        'lor', 'documents', 'photos', 'invoices', 'assessment',
        'isr', 'fsr', 'activity'
    ]
    if request.user.role == User.Role.ADMIN or request.user.is_superuser:
        valid_tabs.append('billing')

    active_tab = request.GET.get('tab', 'overview').lower()
    if active_tab not in valid_tabs:
        active_tab = 'overview'

    # Gather data for tabs
    from surveys.models import Inspection, InspectionPhoto
    from documents.models import ClaimDocument, Requirement
    from assessments.models import Invoice, Assessment
    from reports.models import AuditLog, ILA, ISR, FSR
    from claims.models import ClaimStatusHistory

    assignments = claim.assignments.select_related('surveyor', 'assigned_by').order_by('-assigned_at')
    inspections = claim.inspections.select_related('surveyor').prefetch_related('observations_list').order_by('-inspection_date')
    ila_report = claim.ila_reports.select_related('surveyor', 'prepared_by').order_by('-version_number').first()
    lor_items = claim.requirements.select_related('created_by', 'related_document').order_by('-requested_date')
    claim_documents = claim.documents.select_related('document_type', 'uploaded_by', 'verified_by').order_by('-uploaded_at')
    inspection_photos = InspectionPhoto.objects.filter(
        inspection__claim=claim
    ).select_related('inspection', 'uploaded_by').order_by('-created_at')
    invoices = claim.invoices.select_related('verified_by').order_by('-invoice_date')
    assessment = getattr(claim, 'assessment', None)
    assessment_items = assessment.items.all() if assessment else []
    isr_report = claim.isr_reports.select_related('prepared_by').order_by('-version_number').first()
    fsr_report = claim.fsr_reports.select_related('prepared_by', 'assessment').order_by('-version_number').first()

    # Unified Activity Timeline: ClaimStatusHistory + AuditLog (claim=claim), newest first
    status_histories = list(claim.status_history.select_related('changed_by').all())
    audit_logs = list(AuditLog.objects.filter(claim=claim).select_related('user').all())

    timeline_items = []
    for sh in status_histories:
        timeline_items.append({
            'type': 'status_change',
            'timestamp': sh.changed_at,
            'actor': sh.changed_by.get_full_name() or sh.changed_by.username,
            'title': f"Status changed: {sh.old_status} → {sh.new_status}",
            'description': sh.remarks or "No remarks provided.",
            'badge_color': 'info',
        })

    for al in audit_logs:
        actor = (al.user.get_full_name() or al.user.username) if al.user else "System"
        timeline_items.append({
            'type': 'audit',
            'timestamp': al.timestamp,
            'actor': actor,
            'title': f"{al.action.replace('_', ' ').title()} ({al.model_name})",
            'description': al.description or f"Action {al.action} recorded on {al.model_name} #{al.object_id}.",
            'badge_color': 'secondary' if 'PDF' not in al.action else 'success',
        })

    # Sort descending by timestamp
    timeline_items.sort(key=lambda x: x['timestamp'], reverse=True)

    survey_details = claim.get_survey_details()

    # Instantiate forms for surveyor editing
    inspection_form = None
    lor_form = None
    assessment_financial_form = None
    assessment_item_form = None
    ila_form = None
    isr_form = None
    fsr_form = None
    claim_document_form = ClaimDocumentForm()
    invoice_form = InvoiceForm()

    if request.user.role == User.Role.SURVEYOR:
        # Latest inspection or blank form
        latest_inspection = inspections.first()
        initial_inspection = {}
        if latest_inspection and latest_inspection.observations_list.exists():
            for obs in latest_inspection.observations_list.all():
                if obs.category == 'Extent of Damage':
                    initial_inspection['extent_of_damage'] = obs.description
                elif obs.category == 'Cause':
                    initial_inspection['cause_observations'] = obs.description
                elif obs.category == 'Salvage':
                    initial_inspection['salvage_observations'] = obs.description
        inspection_form = InspectionForm(instance=latest_inspection, initial=initial_inspection)
        lor_form = RequirementForm(claim=claim)
        
        if assessment:
            assessment_financial_form = AssessmentFinancialForm(instance=assessment)
        else:
            assessment_financial_form = AssessmentFinancialForm()
        assessment_item_form = AssessmentItemForm()

        policy_period_str = ""
        if claim.policy.start_datetime and claim.policy.end_datetime:
            policy_period_str = f"{claim.policy.start_datetime.strftime('%d/%m/%Y')} to {claim.policy.end_datetime.strftime('%d/%m/%Y')}"

        ila_form = ILAForm(instance=ila_report) if ila_report else ILAForm(initial={
            'report_number': generate_report_number(claim, 'ILA'),
            'report_date': timezone.localdate(),
            'policy_number': claim.policy.policy_number,
            'policy_type': claim.policy.policy_type,
            'policy_period': policy_period_str,
            'commodity': claim.policy.commodity,
            'sum_insured': claim.policy.sum_insured,
            'policy_excess': claim.policy.excess,
            'inspection_location': claim.loss_location,
            'instruction_date': claim.instruction_date,
            'instruction_source': claim.instruction_source,
            'claimed_amount': claim.claimed_amount,
            'visit_date': latest_inspection.inspection_date if latest_inspection and latest_inspection.inspection_date else timezone.localdate(),
            'visit_start_time': latest_inspection.start_time if latest_inspection and latest_inspection.start_time else '10:00:00',
            'visit_end_time': latest_inspection.end_time if latest_inspection and latest_inspection.end_time else '12:00:00',
            'person_contacted': latest_inspection.person_contacted if latest_inspection and latest_inspection.person_contacted else claim.insured.contact_person,
            'contact_number': latest_inspection.contact_number if latest_inspection and latest_inspection.contact_number else claim.insured.phone,
            'contact_email': claim.insured.email,
            'extent_of_damage': initial_inspection.get('extent_of_damage', ''),
            'cause_of_damage': initial_inspection.get('cause_observations', ''),
            'salvage_prospect': initial_inspection.get('salvage_observations', ''),
        })
        isr_form = ISRForm(instance=isr_report) if isr_report else ISRForm(initial={
            'report_number': generate_report_number(claim, 'ISR'),
        })
        fsr_initial = {
            'report_number': generate_report_number(claim, 'FSR'),
            'sum_insured': claim.policy.sum_insured,
            'value_at_risk': claim.policy.sum_insured,
        }
        if not fsr_report:
            submitted_isr = claim.isr_reports.filter(
                status__in=[ReportStatus.SUBMITTED, ReportStatus.FINAL]
            ).order_by('-submitted_at', '-version_number').first()
            if submitted_isr:
                fsr_initial.update({
                    'introduction': submitted_isr.introduction,
                    'occurrence_details': submitted_isr.occurrence_details,
                    'survey_details': submitted_isr.survey_details,
                    'cause_of_loss': submitted_isr.cause_of_loss,
                    'extent_of_loss': submitted_isr.extent_of_damage,
                })
        fsr_form = FSRForm(instance=fsr_report) if fsr_report else FSRForm(initial=fsr_initial)

    context = {
        'claim': claim,
        'active_tab': active_tab,
        'assignments': assignments,
        'inspections': inspections,
        'ila_report': ila_report,
        'lor_items': lor_items,
        'claim_documents': claim_documents,
        'inspection_photos': inspection_photos,
        'invoices': invoices,
        'assessment': assessment,
        'assessment_items': assessment_items,
        'isr_report': isr_report,
        'fsr_report': fsr_report,
        'timeline_items': timeline_items,
        'survey_details': survey_details,
        'available_surveyors': User.objects.filter(role=User.Role.SURVEYOR, is_active=True).order_by('first_name', 'username'),
        'claim_document_form': claim_document_form,
        'invoice_form': invoice_form,
        # Interactive forms
        'inspection_form': inspection_form,
        'lor_form': lor_form,
        'assessment_financial_form': assessment_financial_form,
        'assessment_item_form': assessment_item_form,
        'ila_form': ila_form,
        'isr_form': isr_form,
        'fsr_form': fsr_form,
        # Billing App Data (Admin Only)
        'service_invoice': claim.service_invoices.exclude(status='CANCELLED').first() if (request.user.role == User.Role.ADMIN or request.user.is_superuser) else None,
        'service_invoice_items': (claim.service_invoices.exclude(status='CANCELLED').first().items.all().order_by('id')) if ((request.user.role == User.Role.ADMIN or request.user.is_superuser) and claim.service_invoices.exclude(status='CANCELLED').exists()) else [],
        'cancelled_service_invoices': claim.service_invoices.filter(status='CANCELLED').order_by('-updated_at') if (request.user.role == User.Role.ADMIN or request.user.is_superuser) else [],
    }
    return render(request, 'claims/claim_detail.html', context)


@admin_required
def claim_assign_surveyor(request, pk):
    """Admin endpoint to assign or reassign a surveyor to a claim from the web portal."""
    claim = get_object_or_404(Claim, pk=pk)
    if request.method == 'POST':
        surveyor_id = request.POST.get('surveyor')
        due_date = request.POST.get('due_date') or None
        instructions = request.POST.get('instructions', '').strip()
        priority = request.POST.get('priority', claim.priority)
        remarks = request.POST.get('remarks', '').strip()

        if not surveyor_id:
            messages.error(request, "Please select a surveyor to assign.")
            return redirect(f'/claims/{claim.id}/?tab=assignment')

        surveyor = get_object_or_404(User, pk=surveyor_id, role=User.Role.SURVEYOR)

        if claim.active_assignment:
            reassign_surveyor(
                claim=claim,
                new_surveyor=surveyor,
                assigned_by=request.user,
                due_date=due_date,
                instructions=instructions,
                priority=priority,
                remarks=remarks or f"Reassigned to {surveyor.get_full_name() or surveyor.username}",
                request=request
            )
            messages.success(request, f"Claim {claim.claim_number} successfully reassigned to {surveyor.get_full_name() or surveyor.username}.")
        else:
            assign_surveyor(
                claim=claim,
                surveyor=surveyor,
                assigned_by=request.user,
                due_date=due_date,
                instructions=instructions,
                priority=priority,
                request=request
            )
            messages.success(request, f"Claim {claim.claim_number} successfully assigned to {surveyor.get_full_name() or surveyor.username}.")

    return redirect(f'/claims/{claim.id}/?tab=assignment')


# --- Claim Creation Wizard (Admin Only) ---

@admin_required
def claim_create(request):
    """
    Multi-section Claim Creation Form (Admin only):
    Section A (Claim), Section B (Insurer), Section C (Insured), Section D (Policy), Section E (Loss)
    With dynamic survey-type-specific detail panel (FIRE, ENG, MARINE, PROPERTY).
    Server decides authoritative survey type and validates only the matching detail form.
    """
    from django.db import transaction
    import json

    survey_types = SurveyType.objects.filter(is_active=True)
    insurers = Insurer.objects.filter(is_active=True).order_by('company_name')
    insured_list = Insured.objects.filter(is_active=True).order_by('name')
    policies = Policy.objects.select_related('insurer').order_by('policy_number')

    # Mapping of policy to insurer for client-side dynamic filtering
    policy_insurer_map = {
        p.id: p.insurer_id for p in policies
    }

    if request.method == 'POST':
        claim_form = ClaimCreateForm(request.POST)
        survey_type_id = request.POST.get('survey_type')
        selected_st = SurveyType.objects.filter(id=survey_type_id).first() if survey_type_id else None
        st_code = selected_st.code.upper() if selected_st else ""

        # Survey-type specific detail form handling
        detail_form = None
        detail_form_map = {
            'FIRE': (FireClaimDetailsForm, 'fire'),
            'ENG': (EngineeringClaimDetailsForm, 'eng'),
            'ENGINEERING': (EngineeringClaimDetailsForm, 'eng'),
            'MAR': (MarineClaimDetailsForm, 'marine'),
            'MARINE': (MarineClaimDetailsForm, 'marine'),
            'PROP': (PropertyClaimDetailsForm, 'property'),
            'PROPERTY': (PropertyClaimDetailsForm, 'property'),
        }

        if st_code in detail_form_map:
            form_cls, prefix = detail_form_map[st_code]
            has_prefixed_data = any(
                k.startswith(f"{prefix}-") and bool(str(v).strip())
                for k, v in request.POST.items()
            )
            has_unprefixed_data = any(
                k in form_cls.base_fields and bool(str(v).strip())
                for k, v in request.POST.items()
            )

            if has_prefixed_data:
                detail_form = form_cls(request.POST, prefix=prefix)
            elif has_unprefixed_data:
                detail_form = form_cls(request.POST)

        is_claim_valid = claim_form.is_valid()
        is_detail_valid = detail_form.is_valid() if detail_form else True

        if is_claim_valid and is_detail_valid:
            with transaction.atomic():
                claim = claim_form.save(commit=False)
                claim.created_by = request.user
                claim.save()

                if detail_form:
                    detail_instance = detail_form.save(commit=False)
                    detail_instance.claim = claim
                    detail_instance.save()

            messages.success(request, f"Claim {claim.claim_number} created successfully!")
            return redirect(f'/claims/{claim.id}/')
        else:
            messages.error(request, "Please correct the errors in the form before submitting.")
    else:
        claim_form = ClaimCreateForm()
        detail_form = None
        st_code = ""

    context = {
        'claim_form': claim_form,
        'detail_form': detail_form,
        'fire_form': detail_form if (detail_form and st_code == 'FIRE') else FireClaimDetailsForm(prefix='fire'),
        'eng_form': detail_form if (detail_form and st_code in ['ENG', 'ENGINEERING']) else EngineeringClaimDetailsForm(prefix='eng'),
        'marine_form': detail_form if (detail_form and st_code in ['MAR', 'MARINE']) else MarineClaimDetailsForm(prefix='marine'),
        'property_form': detail_form if (detail_form and st_code in ['PROP', 'PROPERTY']) else PropertyClaimDetailsForm(prefix='property'),
        'survey_types': survey_types,
        'insurers': insurers,
        'insured_list': insured_list,
        'policies': policies,
        'policy_insurer_map': policy_insurer_map,
        'policy_insurer_map_json': json.dumps(policy_insurer_map),
    }
    return render(request, 'claims/claim_form.html', context)


# --- Surveyor Tab Action Endpoints ---

def _get_claim_for_surveyor(request, pk):
    """Helper ensuring surveyor has active assignment to this claim (or user is admin/superuser)."""
    claim = get_object_or_404(Claim, pk=pk)
    if request.user.role == User.Role.SURVEYOR and not request.user.is_superuser:
        is_assigned = claim.assignments.filter(surveyor=request.user).exclude(
            status=SurveyAssignment.Status.REASSIGNED
        ).exists()
        if not is_assigned:
            raise PermissionDenied("You are not assigned to this claim.")
    elif request.user.role != User.Role.ADMIN and not request.user.is_superuser:
        raise PermissionDenied("Unauthorized role.")
    return claim


@surveyor_required
def claim_inspection_save(request, pk):
    """Surveyor saves or updates an inspection with observations and multi-file attachments."""
    if request.method != 'POST':
        return redirect(f'/claims/{pk}/?tab=inspection')

    claim = _get_claim_for_surveyor(request, pk)
    inspection_id = request.POST.get('inspection_id')
    instance = get_object_or_404(Inspection, pk=inspection_id, claim=claim) if inspection_id else None

    form = InspectionForm(request.POST, request.FILES, instance=instance)
    if form.is_valid():
        from django.db import transaction
        with transaction.atomic():
            inspection = form.save(commit=False)
            inspection.claim = claim
            inspection.surveyor = request.user
            inspection.save()

            # Save uploaded photos
            photos = form.cleaned_data.get('photos') or []
            for p in photos:
                InspectionPhoto.objects.create(
                    inspection=inspection,
                    image=p,
                    uploaded_by=request.user,
                    caption=p.name
                )

            # Save uploaded documents
            docs = form.cleaned_data.get('documents') or []
            if docs:
                doc_type, _ = DocumentType.objects.get_or_create(
                    code='INSP_DOC',
                    defaults={'name': 'Inspection Document', 'is_active': True}
                )
                for d in docs:
                    ClaimDocument.objects.create(
                        claim=claim,
                        document_type=doc_type,
                        file=d,
                        description=f"Inspection attachment ({d.name})",
                        uploaded_by=request.user
                    )

            # Advance status if appropriate
            if inspection.status == Inspection.Status.COMPLETED and claim.status in [ClaimStatus.ASSIGNED, ClaimStatus.INSPECTION_PENDING]:
                transition_claim_status(claim, ClaimStatus.INSPECTION_COMPLETED, request.user, remarks="On-site inspection completed", request=request)
            elif inspection.status == Inspection.Status.SCHEDULED and claim.status == ClaimStatus.ASSIGNED:
                transition_claim_status(claim, ClaimStatus.INSPECTION_PENDING, request.user, remarks="Inspection visit scheduled", request=request)

        messages.success(request, "Inspection details and files saved successfully!")
    else:
        for err in form.errors.values():
            messages.error(request, err.as_text())

    return redirect(f'/claims/{pk}/?tab=inspection')


@surveyor_required
def claim_lor_add(request, pk):
    """Surveyor adds a new LOR Requirement."""
    if request.method != 'POST':
        return redirect(f'/claims/{pk}/?tab=lor')

    claim = _get_claim_for_surveyor(request, pk)
    form = RequirementForm(request.POST, claim=claim)
    if form.is_valid():
        req = form.save(commit=False)
        req.claim = claim
        req.created_by = request.user
        req.save()

        # Advance status if at an allowed preceding status
        if claim.status in [ClaimStatus.ILA_PREPARED, ClaimStatus.REPORT_SUBMITTED, ClaimStatus.INSPECTION_COMPLETED]:
            transition_claim_status(claim, ClaimStatus.LOR_ISSUED, request.user, remarks=f"LOR item requested: {req.description[:30]}", request=request)

        messages.success(request, "Requirement added to LOR successfully.")
    else:
        messages.error(request, "Failed to add requirement. Please check input fields.")

    return redirect(f'/claims/{pk}/?tab=lor')


def claim_lor_update_status(request, pk, req_id):
    """Updates requirement status inline. Verification status change requires Administrator role."""
    if not request.user.is_authenticated:
        return redirect(f"/login/?next={request.path}")
    if request.method != 'POST':
        return redirect(f'/claims/{pk}/?tab=lor')

    claim = _get_claim_for_surveyor(request, pk)
    req = get_object_or_404(Requirement, pk=req_id, claim=claim)
    new_status = request.POST.get('status')

    is_admin = request.user.role == User.Role.ADMIN or request.user.is_superuser
    if (new_status == Requirement.Status.VERIFIED or req.status == Requirement.Status.VERIFIED) and not is_admin:
        messages.error(request, "To change verification status, the logged-in user must be an Administrator.")
        return redirect(f'/claims/{pk}/?tab=lor')

    if new_status in Requirement.Status.values:
        req.status = new_status
        if new_status in [Requirement.Status.RECEIVED, Requirement.Status.VERIFIED] and not req.received_date:
            from django.utils import timezone
            req.received_date = timezone.localdate()
        req.save()
        messages.success(request, f"Requirement status updated to {req.get_status_display()}.")

    return redirect(f'/claims/{pk}/?tab=lor')


@admin_required
def claim_document_verify(request, pk, doc_id):
    """Marks a ClaimDocument as verified by an Administrator."""
    if request.method != 'POST':
        return redirect(f'/claims/{pk}/?tab=documents')

    claim = get_object_or_404(Claim, pk=pk)
    doc = get_object_or_404(ClaimDocument, pk=doc_id, claim=claim)
    from documents.services import verify_claim_document
    verify_claim_document(doc, verified_by=request.user, remarks=request.POST.get('remarks', ''))
    messages.success(request, f"Document '{doc.document_type.name}' verified successfully!")
    return redirect(f'/claims/{pk}/?tab=documents')


def claim_document_upload(request, pk):
    """Upload a ClaimDocument with Ref Number, Date, Type, and File."""
    if not request.user.is_authenticated:
        return redirect(f"/login/?next={request.path}")
    if request.method != 'POST':
        return redirect(f'/claims/{pk}/?tab=documents')

    claim = _get_claim_for_surveyor(request, pk)
    form = ClaimDocumentForm(request.POST, request.FILES)
    if form.is_valid():
        doc = form.save(commit=False)
        doc.claim = claim
        doc.uploaded_by = request.user
        doc.save()
        messages.success(request, f"Document '{doc.document_type.name}' uploaded successfully.")
    else:
        for err in form.errors.values():
            messages.error(request, err.as_text())

    return redirect(f'/claims/{pk}/?tab=documents')


def claim_invoice_add(request, pk):
    """Surveyor or Admin adds a repair/replacement loss invoice for the claim."""
    if not request.user.is_authenticated:
        return redirect(f"/login/?next={request.path}")
    if request.method != 'POST':
        return redirect(f'/claims/{pk}/?tab=invoices')

    claim = _get_claim_for_surveyor(request, pk)
    form = InvoiceForm(request.POST, request.FILES)
    if form.is_valid():
        inv = form.save(commit=False)
        inv.claim = claim
        inv.total_amount = (inv.amount or Decimal('0.00')) + (inv.tax_amount or Decimal('0.00'))
        inv.save()
        messages.success(request, f"Repair invoice #{inv.invoice_number} from '{inv.vendor_name}' added successfully.")
    else:
        for field, errors in form.errors.items():
            for err in errors:
                messages.error(request, f"{field.replace('_', ' ').capitalize()}: {err}")

    return redirect(f'/claims/{pk}/?tab=invoices')


def claim_invoice_delete(request, pk, inv_id):
    """Surveyor or Admin deletes a repair/replacement invoice."""
    if not request.user.is_authenticated:
        return redirect(f"/login/?next={request.path}")
    if request.method != 'POST':
        return redirect(f'/claims/{pk}/?tab=invoices')

    claim = _get_claim_for_surveyor(request, pk)
    inv = get_object_or_404(Invoice, pk=inv_id, claim=claim)
    inv_num = inv.invoice_number
    inv.delete()
    messages.success(request, f"Repair invoice #{inv_num} deleted.")
    return redirect(f'/claims/{pk}/?tab=invoices')


def claim_invoice_verify(request, pk, inv_id):
    """Admin or Surveyor toggles verification status of a repair invoice."""
    if not request.user.is_authenticated:
        return redirect(f"/login/?next={request.path}")
    if request.method != 'POST':
        return redirect(f'/claims/{pk}/?tab=invoices')

    claim = _get_claim_for_surveyor(request, pk)
    inv = get_object_or_404(Invoice, pk=inv_id, claim=claim)
    inv.verified = not inv.verified
    inv.verified_by = request.user if inv.verified else None
    inv.save(update_fields=['verified', 'verified_by', 'updated_at'])
    status_str = "verified" if inv.verified else "marked as pending"
    messages.success(request, f"Repair invoice #{inv.invoice_number} {status_str}.")
    return redirect(f'/claims/{pk}/?tab=invoices')


@surveyor_required
def claim_assessment_save(request, pk):
    """Surveyor updates financial parameters of Assessment and triggers recalculation."""
    if request.method != 'POST':
        return redirect(f'/claims/{pk}/?tab=assessment')

    claim = _get_claim_for_surveyor(request, pk)
    assessment, _ = Assessment.objects.get_or_create(claim=claim, defaults={'created_by': request.user})

    form = AssessmentFinancialForm(request.POST, instance=assessment)
    if form.is_valid():
        assessment = form.save()
        recalculate_assessment(assessment)

        # Status transition to ASSESSMENT_IN_PROGRESS if ready
        if claim.status in [ClaimStatus.LOR_ISSUED, ClaimStatus.DOCUMENT_COLLECTION, ClaimStatus.REPORT_SUBMITTED, ClaimStatus.INSPECTION_COMPLETED, ClaimStatus.ILA_PREPARED]:
            transition_claim_status(claim, ClaimStatus.ASSESSMENT_IN_PROGRESS, request.user, remarks="Financial assessment parameters updated", request=request)

        messages.success(request, "Financial assessment updated and recalculated successfully.")
    else:
        messages.error(request, "Error updating assessment figures.")

    return redirect(f'/claims/{pk}/?tab=assessment')


@surveyor_required
def claim_assessment_item_add(request, pk):
    """Surveyor adds an Assessment line item; server recomputes totals."""
    if request.method != 'POST':
        return redirect(f'/claims/{pk}/?tab=assessment')

    claim = _get_claim_for_surveyor(request, pk)
    assessment, _ = Assessment.objects.get_or_create(claim=claim, defaults={'created_by': request.user})

    form = AssessmentItemForm(request.POST)
    if form.is_valid():
        item = form.save(commit=False)
        item.assessment = assessment
        item.save()
        recalculate_assessment(assessment)
        if claim.status in [ClaimStatus.LOR_ISSUED, ClaimStatus.DOCUMENT_COLLECTION, ClaimStatus.REPORT_SUBMITTED, ClaimStatus.INSPECTION_COMPLETED, ClaimStatus.ILA_PREPARED]:
            transition_claim_status(claim, ClaimStatus.ASSESSMENT_IN_PROGRESS, request.user, remarks="Financial assessment item added", request=request)
        messages.success(request, f"Item '{item.description}' added to assessment.")
    else:
        messages.error(request, "Failed to add assessment item. Please check quantity and rate.")

    return redirect(f'/claims/{pk}/?tab=assessment')


@surveyor_required
def claim_assessment_item_edit(request, pk, item_id):
    """Surveyor updates an existing Assessment line item; server recomputes totals."""
    if request.method != 'POST':
        return redirect(f'/claims/{pk}/?tab=assessment')

    claim = _get_claim_for_surveyor(request, pk)
    if not hasattr(claim, 'assessment'):
        messages.error(request, "Assessment not found.")
        return redirect(f'/claims/{pk}/?tab=assessment')

    item = get_object_or_404(AssessmentItem, pk=item_id, assessment=claim.assessment)
    form = AssessmentItemForm(request.POST, instance=item)
    if form.is_valid():
        form.save()
        recalculate_assessment(claim.assessment)
        messages.success(request, f"Assessment item '{item.description}' updated.")
    else:
        for err in form.errors.values():
            messages.error(request, err.as_text())

    return redirect(f'/claims/{pk}/?tab=assessment')


@surveyor_required
def claim_assessment_item_delete(request, pk, item_id):
    """Surveyor removes an assessment item."""
    if request.method != 'POST':
        return redirect(f'/claims/{pk}/?tab=assessment')

    claim = _get_claim_for_surveyor(request, pk)
    if hasattr(claim, 'assessment'):
        item = get_object_or_404(AssessmentItem, pk=item_id, assessment=claim.assessment)
        item.delete()
        recalculate_assessment(claim.assessment)
        messages.success(request, "Assessment item deleted.")

    return redirect(f'/claims/{pk}/?tab=assessment')


@surveyor_required
def claim_report_save(request, pk, report_type):
    """Surveyor saves or updates draft of ILA, ISR, or FSR."""
    if request.method != 'POST':
        return redirect(f'/claims/{pk}/?tab={report_type}')

    claim = _get_claim_for_surveyor(request, pk)
    report_type = report_type.lower()

    if report_type == 'ila':
        existing = claim.ila_reports.order_by('-version_number').first()
        post_data = request.POST.copy()
        if not post_data.get('policy_number'):
            post_data['policy_number'] = claim.policy.policy_number
        if not post_data.get('policy_type'):
            post_data['policy_type'] = claim.policy.policy_type
        if not post_data.get('commodity'):
            post_data['commodity'] = claim.policy.commodity
        if not post_data.get('sum_insured'):
            post_data['sum_insured'] = str(claim.policy.sum_insured)
        if not post_data.get('policy_excess'):
            post_data['policy_excess'] = str(claim.policy.excess)
        if not post_data.get('instruction_date') and claim.instruction_date:
            post_data['instruction_date'] = claim.instruction_date.strftime('%Y-%m-%d')
        if not post_data.get('instruction_source') and claim.instruction_source:
            post_data['instruction_source'] = claim.instruction_source
        if not post_data.get('inspection_location') and claim.loss_location:
            post_data['inspection_location'] = claim.loss_location
        if not post_data.get('claimed_amount') and claim.claimed_amount:
            post_data['claimed_amount'] = str(claim.claimed_amount)
        if not post_data.get('report_number'):
            post_data['report_number'] = generate_report_number(claim, 'ILA')
        if not post_data.get('report_date'):
            post_data['report_date'] = timezone.localdate().strftime('%Y-%m-%d')

        form = ILAForm(post_data, instance=existing)
        if form.is_valid():
            ila = form.save(commit=False)
            ila.claim = claim
            ila.prepared_by = request.user
            ila.surveyor = request.user
            ila.status = ReportStatus.DRAFT
            ila.save()
            # If claim was at INSPECTION_COMPLETED, transition to ILA_PREPARED
            if claim.status == ClaimStatus.INSPECTION_COMPLETED:
                transition_claim_status(claim, ClaimStatus.ILA_PREPARED, request.user, remarks="ILA draft prepared", request=request)
            messages.success(request, "Immediate Loss Advice (ILA) saved as draft.")
        else:
            for field, errors in form.errors.items():
                for err in errors:
                    messages.error(request, f"{field.replace('_', ' ').title()}: {err}")

    elif report_type == 'isr':
        existing = claim.isr_reports.order_by('-version_number').first()
        post_data = request.POST.copy()
        if not post_data.get('report_number'):
            post_data['report_number'] = generate_report_number(claim, 'ISR')
        form = ISRForm(post_data, instance=existing)
        if form.is_valid():
            skip_justification = request.POST.get('skip_justification', '').strip()
            if not claim.has_completed_lor_and_assessment and not skip_justification:
                messages.error(request, "Reason for skipping LOR/Assessment is required.")
                return redirect(f'/claims/{pk}/?tab=isr')

            isr = form.save(commit=False)
            isr.claim = claim
            isr.prepared_by = request.user
            isr.status = ReportStatus.DRAFT
            isr.save()

            if claim.status != ClaimStatus.ISR_PREPARED:
                from claims.services import ALLOWED_TRANSITIONS
                if ClaimStatus.ISR_PREPARED in ALLOWED_TRANSITIONS.get(claim.status, set()):
                    remarks = f"Justification for skipping LOR/Assessment: {skip_justification}" if skip_justification else "ISR draft prepared"
                    try:
                        transition_claim_status(claim, ClaimStatus.ISR_PREPARED, request.user, remarks=remarks, request=request)
                    except ValidationError as e:
                        messages.error(request, str(e))
                        return redirect(f'/claims/{pk}/?tab=isr')
            messages.success(request, "Initial Survey Report (ISR) saved as draft.")
        else:
            for field, errors in form.errors.items():
                for err in errors:
                    messages.error(request, f"{field.replace('_', ' ').title()}: {err}")

    elif report_type == 'fsr':
        existing = claim.fsr_reports.order_by('-version_number').first()
        post_data = request.POST.copy()
        if not post_data.get('report_number'):
            post_data['report_number'] = generate_report_number(claim, 'FSR')
        form = FSRForm(post_data, instance=existing)
        if form.is_valid():
            skip_justification = request.POST.get('skip_justification', '').strip()
            if not claim.has_completed_lor_and_assessment and not skip_justification:
                messages.error(request, "Reason for skipping LOR/Assessment is required.")
                return redirect(f'/claims/{pk}/?tab=fsr')

            fsr = form.save(commit=False)
            fsr.claim = claim
            fsr.prepared_by = request.user
            fsr.assessment = getattr(claim, 'assessment', None)
            fsr.status = ReportStatus.DRAFT
            fsr.save()

            if claim.status != ClaimStatus.FSR_PREPARED:
                from claims.services import ALLOWED_TRANSITIONS
                if ClaimStatus.FSR_PREPARED in ALLOWED_TRANSITIONS.get(claim.status, set()):
                    remarks = f"Justification for skipping LOR/Assessment: {skip_justification}" if skip_justification else "FSR draft prepared"
                    try:
                        transition_claim_status(claim, ClaimStatus.FSR_PREPARED, request.user, remarks=remarks, request=request)
                    except ValidationError as e:
                        messages.error(request, str(e))
                        return redirect(f'/claims/{pk}/?tab=fsr')
            messages.success(request, "Final Survey Report (FSR) saved as draft.")
        else:
            for field, errors in form.errors.items():
                for err in errors:
                    messages.error(request, f"{field.replace('_', ' ').title()}: {err}")

    return redirect(f'/claims/{pk}/?tab={report_type}')


@surveyor_required
def claim_report_submit(request, pk, report_type):
    """Surveyor submits ILA, ISR, or FSR report (calls submit_report from services.py)."""
    if request.method != 'POST':
        return redirect(f'/claims/{pk}/?tab={report_type}')

    claim = _get_claim_for_surveyor(request, pk)
    report_type = report_type.lower()
    report = None

    if report_type == 'ila':
        report = claim.ila_reports.order_by('-version_number').first()
    elif report_type == 'isr':
        report = claim.isr_reports.order_by('-version_number').first()
    elif report_type == 'fsr':
        report = claim.fsr_reports.order_by('-version_number').first()

    if not report:
        messages.error(request, f"No {report_type.upper()} report found to submit.")
        return redirect(f'/claims/{pk}/?tab={report_type}')

    if report.status != ReportStatus.DRAFT:
        messages.warning(request, f"Report is already in '{report.get_status_display()}' status.")
        return redirect(f'/claims/{pk}/?tab={report_type}')

    try:
        submit_report(claim, report, request.user, request=request)
        save_report_pdf_as_document(report, request.user, request=request)
        messages.success(request, f"{report_type.upper()} report {report.report_number} submitted successfully!")
    except Exception as e:
        messages.error(request, f"Failed to submit report: {str(e)}")

    return redirect(f'/claims/{pk}/?tab={report_type}')


def claim_report_preview(request, pk, report_type):
    """Inline browser preview of the report PDF."""
    from django.http import HttpResponse
    claim = _get_claim_for_surveyor(request, pk)
    report_type = report_type.lower()
    report = None

    if report_type == 'ila':
        report = claim.ila_reports.order_by('-version_number').first()
    elif report_type == 'isr':
        report = claim.isr_reports.order_by('-version_number').first()
    elif report_type == 'fsr':
        report = claim.fsr_reports.order_by('-version_number').first()

    if not report:
        messages.error(request, "Report not found.")
        return redirect(f'/claims/{pk}/?tab={report_type}')

    pdf_bytes = generate_report_pdf(report)
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="{report.report_number}.pdf"'
    return response


def claim_report_generate_pdf(request, pk, report_type):
    """Generate and save report PDF as a ClaimDocument."""
    if request.method != 'POST':
        return redirect(f'/claims/{pk}/?tab={report_type}')

    claim = _get_claim_for_surveyor(request, pk)
    report_type = report_type.lower()
    report = None

    if report_type == 'ila':
        report = claim.ila_reports.order_by('-version_number').first()
    elif report_type == 'isr':
        report = claim.isr_reports.order_by('-version_number').first()
    elif report_type == 'fsr':
        report = claim.fsr_reports.order_by('-version_number').first()

    if not report:
        messages.error(request, "Report not found.")
        return redirect(f'/claims/{pk}/?tab={report_type}')

    doc = save_report_pdf_as_document(report, request.user, request=request)
    messages.success(request, f"Report PDF saved as Claim Document #{doc.pk}.")
    return redirect(f'/claims/{pk}/?tab={report_type}')


@admin_required
def claim_approve_and_close(request, pk):
    """
    Admin-only action: finalise the latest submitted report and close the claim
    in a single atomic operation.

    Requirements:
      - POST only, with a non-blank 'remarks' field.
      - The claim must have a latest_submitted_report whose status is SUBMITTED.
      - Sets that report's status to FINAL and saves it, then calls close_claim().
    """
    claim = get_object_or_404(Claim, pk=pk)

    if request.method != 'POST':
        return redirect(f'/claims/{pk}/?tab=overview')

    remarks = request.POST.get('remarks', '').strip()
    if not remarks:
        messages.error(request, "Approval remarks are required to close this claim.")
        return redirect(f'/claims/{pk}/?tab=overview')

    report = claim.latest_submitted_report
    if report is None:
        messages.error(request, "Cannot close claim: no submitted report found. Please ensure a report has been submitted first.")
        return redirect(f'/claims/{pk}/?tab=overview')

    if report.status != ReportStatus.SUBMITTED:
        messages.error(request, f"Cannot close claim: the latest report is '{report.get_status_display()}', not Submitted.")
        return redirect(f'/claims/{pk}/?tab=overview')

    try:
        with transaction.atomic():
            report.status = ReportStatus.FINAL
            report.save(update_fields=['status', 'updated_at'])
            close_claim(claim, request.user, remarks=remarks, request=request)
    except ValidationError as exc:
        err_msg = exc.message if hasattr(exc, 'message') else '; '.join(exc.messages) if hasattr(exc, 'messages') else str(exc)
        messages.error(request, f"Close failed: {err_msg}")
        return redirect(f'/claims/{pk}/?tab=overview')

    messages.success(request, f"Claim {claim.claim_number} has been approved and closed.")
    return redirect(f'/claims/{pk}/?tab=activity')


# --- Surveyors Views ---

@admin_required
def surveyor_list(request):
    surveyors = User.objects.filter(role=User.Role.SURVEYOR).select_related('surveyor_profile').order_by('username')
    return render(request, 'surveyors/surveyor_list.html', {'surveyors': surveyors})


@admin_required
def surveyor_add(request):
    if request.method == 'POST':
        form = SurveyorCreateForm(request.POST)
        if form.is_valid():
            profile = form.save()
            messages.success(request, f"Surveyor {profile.user.username} successfully added.")
            return redirect('/surveyors/')
    else:
        form = SurveyorCreateForm()
    return render(request, 'surveyors/surveyor_form.html', {'form': form, 'title': 'Add New Surveyor'})


@admin_required
def surveyor_edit(request, pk):
    user = get_object_or_404(User, pk=pk, role=User.Role.SURVEYOR)
    profile, _ = SurveyorProfile.objects.get_or_create(
        user=user,
        defaults={'license_number': f'LIC-{user.id:04d}', 'license_expiry': '2027-12-31'}
    )
    if request.method == 'POST':
        form = SurveyorUpdateForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, f"Surveyor {user.username} updated successfully.")
            return redirect('/surveyors/')
    else:
        form = SurveyorUpdateForm(instance=profile)
    return render(request, 'surveyors/surveyor_form.html', {'form': form, 'title': f'Edit Surveyor: {user.username}'})


@admin_required
def surveyor_workload(request):
    surveyors = User.objects.filter(role=User.Role.SURVEYOR).select_related('surveyor_profile')
    workload_data = []
    for s in surveyors:
        # All non-reassigned assignments for this surveyor
        all_assignments = SurveyAssignment.objects.filter(
            surveyor=s
        ).exclude(status=SurveyAssignment.Status.REASSIGNED).select_related('claim')

        assigned_count = 0       # Assignment is ASSIGNED and claim is open/active
        in_progress_count = 0    # Assignment is IN_PROGRESS (inspection underway or later)
        completed_count = 0      # Assignment is COMPLETED and claim is NOT yet closed
        closed_count = 0         # Claim is CLOSED (survey fully done)

        for a in all_assignments:
            claim_status = a.claim.status
            if claim_status == ClaimStatus.CLOSED:
                closed_count += 1
            elif a.status == SurveyAssignment.Status.ASSIGNED:
                assigned_count += 1
            elif a.status == SurveyAssignment.Status.IN_PROGRESS:
                in_progress_count += 1
            elif a.status == SurveyAssignment.Status.COMPLETED:
                completed_count += 1

        total_active = assigned_count + in_progress_count

        workload_data.append({
            'surveyor': s,
            'assigned_count': assigned_count,
            'in_progress_count': in_progress_count,
            'completed_count': completed_count,
            'closed_count': closed_count,
            'total_active': total_active,
        })

    return render(request, 'surveyors/surveyor_workload.html', {'workload_data': workload_data})



# --- Insurers Views ---

@admin_required
def insurer_list(request):
    insurers = Insurer.objects.all().order_by('company_name', 'branch_name')
    return render(request, 'insurers/insurer_list.html', {'insurers': insurers})


@admin_required
def insurer_add(request):
    if request.method == 'POST':
        form = InsurerForm(request.POST)
        if form.is_valid():
            insurer = form.save()
            messages.success(request, f"Insurer {insurer.company_name} ({insurer.branch_name}) created successfully.")
            return redirect('/insurers/')
    else:
        form = InsurerForm()
    return render(request, 'insurers/insurer_form.html', {'form': form, 'title': 'Add New Insurer'})


@admin_required
def insurer_edit(request, pk):
    insurer = get_object_or_404(Insurer, pk=pk)
    if request.method == 'POST':
        form = InsurerForm(request.POST, instance=insurer)
        if form.is_valid():
            form.save()
            messages.success(request, f"Insurer {insurer.company_name} updated successfully.")
            return redirect('/insurers/')
    else:
        form = InsurerForm(instance=insurer)
    return render(request, 'insurers/insurer_form.html', {'form': form, 'title': f'Edit Insurer: {insurer.company_name}'})


# --- Insured Views ---

@admin_required
def insured_list(request):
    insured_parties = Insured.objects.all().order_by('name')
    return render(request, 'insured/insured_list.html', {'insured_parties': insured_parties})


@admin_required
def insured_add(request):
    if request.method == 'POST':
        form = InsuredForm(request.POST)
        if form.is_valid():
            insured = form.save()
            messages.success(request, f"Insured party {insured.name} created successfully.")
            return redirect('/insured/')
    else:
        form = InsuredForm()
    return render(request, 'insured/insured_form.html', {'form': form, 'title': 'Add New Insured Party'})


@admin_required
def insured_edit(request, pk):
    insured = get_object_or_404(Insured, pk=pk)
    if request.method == 'POST':
        form = InsuredForm(request.POST, instance=insured)
        if form.is_valid():
            form.save()
            messages.success(request, f"Insured party {insured.name} updated successfully.")
            return redirect('/insured/')
    else:
        form = InsuredForm(instance=insured)
    return render(request, 'insured/insured_form.html', {'form': form, 'title': f'Edit Insured: {insured.name}'})


# --- Policies Views ---

@admin_required
def policy_list(request):
    policies = Policy.objects.select_related('insurer').all().order_by('-created_at')
    return render(request, 'policies/policy_list.html', {'policies': policies})


@admin_required
def policy_add(request):
    if request.method == 'POST':
        form = PolicyForm(request.POST)
        if form.is_valid():
            policy = form.save()
            messages.success(request, f"Policy {policy.policy_number} created successfully.")
            return redirect('/policies/')
    else:
        form = PolicyForm()
    return render(request, 'policies/policy_form.html', {'form': form, 'title': 'Add New Policy'})


@admin_required
def policy_edit(request, pk):
    policy = get_object_or_404(Policy, pk=pk)
    if request.method == 'POST':
        form = PolicyForm(request.POST, instance=policy)
        if form.is_valid():
            form.save()
            messages.success(request, f"Policy {policy.policy_number} updated successfully.")
            return redirect('/policies/')
    else:
        form = PolicyForm(instance=policy)
    return render(request, 'policies/policy_form.html', {'form': form, 'title': f'Edit Policy: {policy.policy_number}'})


# --- Operational Supporting Views ---

@admin_required
def document_list(request):
    documents = ClaimDocument.objects.select_related('claim', 'document_type', 'uploaded_by').order_by('-uploaded_at')[:100]
    return render(request, 'documents/document_list.html', {'documents': documents})


@admin_required
def report_list(request):
    ilas = ILA.objects.select_related('claim', 'surveyor', 'prepared_by').order_by('-created_at')[:30]
    isrs = ISR.objects.select_related('claim', 'prepared_by').order_by('-created_at')[:30]
    fsrs = FSR.objects.select_related('claim', 'prepared_by', 'assessment').order_by('-created_at')[:30]
    return render(request, 'reports/report_list.html', {'ilas': ilas, 'isrs': isrs, 'fsrs': fsrs})


@admin_required
def master_survey_types(request):
    types = SurveyType.objects.all().order_by('name')
    return render(request, 'master/master_survey_types.html', {'types': types})


@admin_required
def master_document_types(request):
    types = DocumentType.objects.all().order_by('name')
    return render(request, 'master/master_document_types.html', {'types': types})


@admin_required
def master_claim_statuses(request):
    statuses = ClaimStatus.choices
    return render(request, 'master/master_claim_statuses.html', {'statuses': statuses})


@admin_required
def user_list(request):
    users = User.objects.all().order_by('username')
    return render(request, 'users/user_list.html', {'users': users})


@admin_required
def audit_list(request):
    logs = AuditLog.objects.select_related('user').order_by('-timestamp')[:100]
    return render(request, 'audit/audit_list.html', {'logs': logs})
