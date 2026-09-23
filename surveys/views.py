from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from accounts.permissions import (
    IsAdminRole,
    IsAssignedSurveyorOrAdmin,
    ClaimScopedQuerySetMixin,
)
from .models import SurveyType, Inspection
from .serializers import SurveyTypeSerializer, InspectionSerializer


class SurveyTypeViewSet(viewsets.ReadOnlyModelViewSet):
    """API endpoint for listing and retrieving survey types."""
    queryset = SurveyType.objects.filter(is_active=True)
    serializer_class = SurveyTypeSerializer
    permission_classes = [IsAuthenticated]


class InspectionViewSet(ClaimScopedQuerySetMixin, viewsets.ModelViewSet):
    """
    API endpoint for viewing and updating inspections.
    Claim-scoped: only accessible by assigned surveyors or admins.
    """
    queryset = Inspection.objects.all()
    serializer_class = InspectionSerializer
    permission_classes = [IsAssignedSurveyorOrAdmin]
    claim_lookup_field = 'claim'
