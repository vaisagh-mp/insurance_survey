from django.db import transaction
from django.utils import timezone
from .models import Inspection


@transaction.atomic
def complete_inspection(inspection, observations="", status_choice=Inspection.Status.COMPLETED):
    """
    Marks an inspection as completed, optionally updating its observations.
    """
    inspection.status = status_choice
    if observations:
        inspection.observations = observations
    inspection.save(update_fields=['status', 'observations', 'updated_at'])
    return inspection
