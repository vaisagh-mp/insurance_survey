from django.db import transaction
from django.utils import timezone
from .models import ClaimDocument, Requirement


@transaction.atomic
def verify_claim_document(document, verified_by, remarks=""):
    """
    Marks a claim document as verified by an authorized user.
    """
    document.verified = True
    document.verified_by = verified_by
    document.verified_at = timezone.now()
    if remarks:
        document.remarks = remarks
    document.save(update_fields=['verified', 'verified_by', 'verified_at', 'remarks'])
    return document


@transaction.atomic
def update_requirement_status(requirement, new_status, received_date=None, remarks=""):
    """
    Updates the status of a document requirement (LOR item).
    """
    requirement.status = new_status
    if received_date is not None:
        requirement.received_date = received_date
    elif new_status == Requirement.Status.RECEIVED and requirement.received_date is None:
        requirement.received_date = timezone.now().date()
    if remarks:
        requirement.remarks = remarks
    requirement.save(update_fields=['status', 'received_date', 'remarks', 'updated_at'])
    return requirement
