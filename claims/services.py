from datetime import timedelta
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from claims.models import Claim, ClaimStatus, ClaimStatusHistory, SurveyAssignment, Priority
from reports.models import ReportStatus
from reports.services import log_action

# Allowed status transitions map
# Allows sensible progression and skipping ahead, while preventing nonsensical jumps (e.g. CLOSED back to NEW)
ALLOWED_TRANSITIONS = {
    ClaimStatus.NEW: {
        ClaimStatus.ASSIGNED,
        ClaimStatus.INSPECTION_PENDING,
        ClaimStatus.ON_HOLD,
        ClaimStatus.CANCELLED,
    },
    ClaimStatus.ASSIGNED: {
        ClaimStatus.INSPECTION_PENDING,
        ClaimStatus.INSPECTION_COMPLETED,
        ClaimStatus.DOCUMENT_COLLECTION,
        ClaimStatus.ON_HOLD,
        ClaimStatus.CANCELLED,
    },
    ClaimStatus.INSPECTION_PENDING: {
        ClaimStatus.INSPECTION_COMPLETED,
        ClaimStatus.ILA_PREPARED,
        ClaimStatus.DOCUMENT_COLLECTION,
        ClaimStatus.ON_HOLD,
        ClaimStatus.CANCELLED,
    },
    ClaimStatus.INSPECTION_COMPLETED: {
        ClaimStatus.ILA_PREPARED,
        ClaimStatus.LOR_ISSUED,
        ClaimStatus.DOCUMENT_COLLECTION,
        ClaimStatus.ASSESSMENT_IN_PROGRESS,
        ClaimStatus.ISR_PREPARED,
        ClaimStatus.FSR_PREPARED,
        ClaimStatus.ON_HOLD,
        ClaimStatus.CANCELLED,
    },
    ClaimStatus.ILA_PREPARED: {
        ClaimStatus.REPORT_SUBMITTED,
        ClaimStatus.LOR_ISSUED,
        ClaimStatus.DOCUMENT_COLLECTION,
        ClaimStatus.ASSESSMENT_IN_PROGRESS,
        ClaimStatus.ISR_PREPARED,
        ClaimStatus.FSR_PREPARED,
        ClaimStatus.ON_HOLD,
        ClaimStatus.CANCELLED,
    },
    ClaimStatus.LOR_ISSUED: {
        ClaimStatus.DOCUMENT_COLLECTION,
        ClaimStatus.ASSESSMENT_IN_PROGRESS,
        ClaimStatus.ISR_PREPARED,
        ClaimStatus.FSR_PREPARED,
        ClaimStatus.QUERY_RAISED,
        ClaimStatus.ON_HOLD,
        ClaimStatus.CANCELLED,
    },
    ClaimStatus.DOCUMENT_COLLECTION: {
        ClaimStatus.LOR_ISSUED,
        ClaimStatus.ASSESSMENT_IN_PROGRESS,
        ClaimStatus.ISR_PREPARED,
        ClaimStatus.FSR_PREPARED,
        ClaimStatus.QUERY_RAISED,
        ClaimStatus.ON_HOLD,
        ClaimStatus.CANCELLED,
    },
    ClaimStatus.ASSESSMENT_IN_PROGRESS: {
        ClaimStatus.DOCUMENT_COLLECTION,
        ClaimStatus.ISR_PREPARED,
        ClaimStatus.FSR_PREPARED,
        ClaimStatus.QUERY_RAISED,
        ClaimStatus.ON_HOLD,
        ClaimStatus.CANCELLED,
    },
    ClaimStatus.ISR_PREPARED: {
        ClaimStatus.DOCUMENT_COLLECTION,
        ClaimStatus.ASSESSMENT_IN_PROGRESS,
        ClaimStatus.FSR_PREPARED,
        ClaimStatus.REPORT_SUBMITTED,
        ClaimStatus.QUERY_RAISED,
        ClaimStatus.ON_HOLD,
        ClaimStatus.CANCELLED,
    },
    ClaimStatus.FSR_PREPARED: {
        ClaimStatus.REPORT_SUBMITTED,
        ClaimStatus.REVISION_REQUIRED,
        ClaimStatus.QUERY_RAISED,
        ClaimStatus.CLOSED,
        ClaimStatus.ON_HOLD,
        ClaimStatus.CANCELLED,
    },
    ClaimStatus.REPORT_SUBMITTED: {
        ClaimStatus.LOR_ISSUED,
        ClaimStatus.DOCUMENT_COLLECTION,
        ClaimStatus.ASSESSMENT_IN_PROGRESS,
        ClaimStatus.ISR_PREPARED,
        ClaimStatus.FSR_PREPARED,
        ClaimStatus.QUERY_RAISED,
        ClaimStatus.REVISION_REQUIRED,
        ClaimStatus.RESUBMITTED,
        ClaimStatus.CLOSED,
        ClaimStatus.ON_HOLD,
        ClaimStatus.CANCELLED,
    },
    ClaimStatus.QUERY_RAISED: {
        ClaimStatus.DOCUMENT_COLLECTION,
        ClaimStatus.ASSESSMENT_IN_PROGRESS,
        ClaimStatus.REVISION_REQUIRED,
        ClaimStatus.RESUBMITTED,
        ClaimStatus.REPORT_SUBMITTED,
        ClaimStatus.ON_HOLD,
        ClaimStatus.CANCELLED,
    },
    ClaimStatus.REVISION_REQUIRED: {
        ClaimStatus.ASSESSMENT_IN_PROGRESS,
        ClaimStatus.FSR_PREPARED,
        ClaimStatus.RESUBMITTED,
        ClaimStatus.REPORT_SUBMITTED,
        ClaimStatus.ON_HOLD,
        ClaimStatus.CANCELLED,
    },
    ClaimStatus.RESUBMITTED: {
        ClaimStatus.REPORT_SUBMITTED,
        ClaimStatus.QUERY_RAISED,
        ClaimStatus.REVISION_REQUIRED,
        ClaimStatus.CLOSED,
        ClaimStatus.ON_HOLD,
        ClaimStatus.CANCELLED,
    },
    ClaimStatus.ON_HOLD: {
        ClaimStatus.NEW,
        ClaimStatus.ASSIGNED,
        ClaimStatus.INSPECTION_PENDING,
        ClaimStatus.INSPECTION_COMPLETED,
        ClaimStatus.ILA_PREPARED,
        ClaimStatus.LOR_ISSUED,
        ClaimStatus.DOCUMENT_COLLECTION,
        ClaimStatus.ASSESSMENT_IN_PROGRESS,
        ClaimStatus.ISR_PREPARED,
        ClaimStatus.FSR_PREPARED,
        ClaimStatus.REPORT_SUBMITTED,
        ClaimStatus.QUERY_RAISED,
        ClaimStatus.REVISION_REQUIRED,
        ClaimStatus.RESUBMITTED,
        ClaimStatus.CANCELLED,
    },
    ClaimStatus.CLOSED: {
        ClaimStatus.QUERY_RAISED,
        ClaimStatus.REVISION_REQUIRED,
        ClaimStatus.ON_HOLD,
    },
    ClaimStatus.CANCELLED: {
        ClaimStatus.ON_HOLD,
        ClaimStatus.NEW,
    },
}


@transaction.atomic
def transition_claim_status(claim, new_status, user, remarks="", request=None, allow_same_status=False):
    """
    Safely transition a claim to a new status.
    
    - Validates against ALLOWED_TRANSITIONS (unless allow_same_status=True).
    - Updates claim.status and saves the claim.
    - Creates a ClaimStatusHistory record.
    - Logs the action via AuditLog.
    - Raises ValidationError on invalid transitions.
    """
    if claim.status == new_status and not allow_same_status:
        raise ValidationError(f"Claim {claim.claim_number} is already in status '{new_status}'.")

    valid_choices = {choice[0] for choice in ClaimStatus.choices}
    if new_status not in valid_choices:
        raise ValidationError(f"'{new_status}' is not a valid ClaimStatus.")

    if claim.status != new_status:
        allowed = ALLOWED_TRANSITIONS.get(claim.status, set())
        if new_status not in allowed:
            raise ValidationError(
                f"Invalid status transition from '{claim.status}' to '{new_status}'. "
                f"Allowed transitions from '{claim.status}': {', '.join(sorted(allowed)) if allowed else 'None'}."
            )

        # Mandatory justification for skip-ahead transitions into ISR_PREPARED or FSR_PREPARED
        if new_status in (ClaimStatus.ISR_PREPARED, ClaimStatus.FSR_PREPARED):
            has_lor = ClaimStatusHistory.objects.filter(claim=claim, new_status=ClaimStatus.LOR_ISSUED).exists() or claim.requirements.exists()
            has_assessment = ClaimStatusHistory.objects.filter(claim=claim, new_status=ClaimStatus.ASSESSMENT_IN_PROGRESS).exists() or hasattr(claim, 'assessment')
            if (not has_lor or not has_assessment) and not (remarks and remarks.strip()):
                missing = []
                if not has_lor:
                    missing.append("LOR Issued")
                if not has_assessment:
                    missing.append("Assessment In Progress")
                raise ValidationError(
                    f"Justification is required to skip {' and '.join(missing)} stage(s)."
                )

    old_status = claim.status
    claim.status = new_status
    claim.save(update_fields=['status', 'updated_at'])

    ClaimStatusHistory.objects.create(
        claim=claim,
        old_status=old_status,
        new_status=new_status,
        changed_by=user,
        remarks=remarks
    )

    log_action(
        user=user,
        action="CLAIM_STATUS_TRANSITION",
        obj=claim,
        description=f"Status transitioned from {old_status} to {new_status}. Remarks: {remarks}".strip(),
        request=request,
        claim=claim
    )

    return claim


@transaction.atomic
def assign_surveyor(claim, surveyor, assigned_by, due_date=None, instructions="", priority=Priority.MEDIUM, request=None):
    """
    Creates/updates the SurveyAssignment and calls transition_claim_status(claim, "ASSIGNED", assigned_by).
    """
    if due_date is None:
        due_date = timezone.now().date() + timedelta(days=14)

    assignment = SurveyAssignment.objects.create(
        claim=claim,
        surveyor=surveyor,
        assigned_by=assigned_by,
        due_date=due_date,
        priority=priority,
        instructions=instructions,
        status=SurveyAssignment.Status.ASSIGNED
    )

    transition_claim_status(
        claim=claim,
        new_status=ClaimStatus.ASSIGNED,
        user=assigned_by,
        remarks=f"Surveyor {surveyor.username} assigned",
        request=request
    )
    return assignment


@transaction.atomic
def reassign_surveyor(claim, new_surveyor, assigned_by, due_date=None, instructions="", priority=Priority.MEDIUM, remarks="", request=None):
    """
    Closes out old SurveyAssignment (status set to REASSIGNED, keeping history) and creates a new one.
    Deliberately does NOT call transition_claim_status here: a claim being reassigned may already
    be in progress (mid-inspection, mid-assessment, etc.), and forcing status back to ASSIGNED
    would be an invalid backward transition.
    """
    if due_date is None:
        due_date = timezone.now().date() + timedelta(days=14)

    # Mark all previous active assignments as REASSIGNED (triggers SurveyAssignment.save log)
    old_assignments = claim.assignments.exclude(status=SurveyAssignment.Status.REASSIGNED)
    for old_assignment in old_assignments:
        old_assignment.status = SurveyAssignment.Status.REASSIGNED
        old_assignment.save()

    new_assignment = SurveyAssignment.objects.create(
        claim=claim,
        surveyor=new_surveyor,
        assigned_by=assigned_by,
        due_date=due_date,
        priority=priority,
        instructions=instructions,
        status=SurveyAssignment.Status.ASSIGNED,
        remarks=remarks
    )

    log_action(
        user=assigned_by,
        action="SURVEYOR_REASSIGNED",
        obj=new_assignment,
        description=f"Claim reassigned to {new_surveyor.username}. Remarks: {remarks}".strip(),
        request=request,
        claim=claim
    )

    return new_assignment


@transaction.atomic
def submit_report(claim, report, submitted_by, request=None):
    """
    Validates the report status is DRAFT, sets it to SUBMITTED with submitted_at=now,
    and calls transition_claim_status(claim, "REPORT_SUBMITTED", submitted_by).
    """
    if report is None:
        report = (
            claim.fsr_reports.order_by('-created_at').first() or
            claim.isr_reports.order_by('-created_at').first() or
            claim.ila_reports.order_by('-created_at').first()
        )

    if report is None:
        raise ValidationError(f"No report found on claim {claim.claim_number} to submit.")

    if report.status != ReportStatus.DRAFT:
        raise ValidationError(
            f"Cannot submit report {report.report_number}: current status is '{report.status}', expected '{ReportStatus.DRAFT}'."
        )

    report.status = ReportStatus.SUBMITTED
    report.submitted_at = timezone.now()
    report.save(update_fields=['status', 'submitted_at', 'updated_at'])

    transition_claim_status(
        claim=claim,
        new_status=ClaimStatus.REPORT_SUBMITTED,
        user=submitted_by,
        remarks=f"Report {report.report_number} submitted",
        request=request,
        allow_same_status=True
    )
    return report


@transaction.atomic
def raise_query(claim, raised_by, remarks="", request=None):
    """
    Sets relevant report(s) status to QUERY and calls transition_claim_status(claim, "QUERY_RAISED", raised_by, remarks).
    """
    reports = list(claim.fsr_reports.filter(status=ReportStatus.SUBMITTED)) + \
              list(claim.isr_reports.filter(status=ReportStatus.SUBMITTED)) + \
              list(claim.ila_reports.filter(status=ReportStatus.SUBMITTED))

    if not reports:
        latest = (
            claim.fsr_reports.order_by('-created_at').first() or
            claim.isr_reports.order_by('-created_at').first() or
            claim.ila_reports.order_by('-created_at').first()
        )
        if latest:
            reports = [latest]

    for report in reports:
        report.status = ReportStatus.QUERY
        report.save(update_fields=['status', 'updated_at'])

    transition_claim_status(
        claim=claim,
        new_status=ClaimStatus.QUERY_RAISED,
        user=raised_by,
        remarks=remarks,
        request=request
    )
    return claim


@transaction.atomic
def respond_query(claim, report, responded_by, remarks="", request=None):
    """
    Bumps report.version_number, sets status back to DRAFT,
    and calls transition_claim_status(claim, "RESUBMITTED", responded_by).
    """
    if report is None:
        report = (
            claim.fsr_reports.filter(status=ReportStatus.QUERY).order_by('-created_at').first() or
            claim.isr_reports.filter(status=ReportStatus.QUERY).order_by('-created_at').first() or
            claim.ila_reports.filter(status=ReportStatus.QUERY).order_by('-created_at').first()
        )
        if report is None:
            report = (
                claim.fsr_reports.order_by('-created_at').first() or
                claim.isr_reports.order_by('-created_at').first() or
                claim.ila_reports.order_by('-created_at').first()
            )

    if report is None:
        raise ValidationError(f"No report found on claim {claim.claim_number} to respond to query.")

    report.version_number += 1
    report.status = ReportStatus.DRAFT
    report.save(update_fields=['version_number', 'status', 'updated_at'])

    transition_claim_status(
        claim=claim,
        new_status=ClaimStatus.RESUBMITTED,
        user=responded_by,
        remarks=remarks or f"Query responded for report {report.report_number} (v{report.version_number})",
        request=request
    )
    return report


@transaction.atomic
def close_claim(claim, closed_by, remarks="", request=None):
    """
    Only allowed if at least one report is FINAL.
    Calls transition_claim_status(claim, "CLOSED", closed_by, remarks).
    """
    has_final_report = (
        claim.fsr_reports.filter(status=ReportStatus.FINAL).exists() or
        claim.isr_reports.filter(status=ReportStatus.FINAL).exists() or
        claim.ila_reports.filter(status=ReportStatus.FINAL).exists()
    )
    if not has_final_report:
        raise ValidationError("Cannot close claim: At least one report must be marked as FINAL.")

    return transition_claim_status(
        claim=claim,
        new_status=ClaimStatus.CLOSED,
        user=closed_by,
        remarks=remarks,
        request=request
    )

