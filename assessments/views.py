from rest_framework import viewsets
from accounts.permissions import (
    IsAssignedSurveyorOrAdmin,
    ClaimScopedQuerySetMixin,
)
from .models import Assessment
from .serializers import AssessmentSerializer
from .services import recalculate_assessment


class AssessmentViewSet(ClaimScopedQuerySetMixin, viewsets.ModelViewSet):
    """
    API endpoint for viewing and updating loss assessments.
    Automatically recalculates assessment totals on save/update.
    Claim-scoped: accessible only by assigned surveyors or admins.
    """
    queryset = Assessment.objects.all()
    serializer_class = AssessmentSerializer
    permission_classes = [IsAssignedSurveyorOrAdmin]
    claim_lookup_field = 'claim'

    def perform_create(self, serializer):
        instance = serializer.save(created_by=self.request.user)
        recalculate_assessment(instance)

    def perform_update(self, serializer):
        instance = serializer.save()
        recalculate_assessment(instance)
