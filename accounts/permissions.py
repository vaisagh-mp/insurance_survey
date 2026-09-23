from rest_framework.permissions import BasePermission
from claims.models import Claim, SurveyAssignment


class IsAdminRole(BasePermission):
    """Allows access only to users with role=ADMIN or superusers."""

    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            (request.user.role == 'ADMIN' or request.user.is_superuser)
        )


class IsAssignedSurveyorOrAdmin(BasePermission):
    """
    Permission class for claim-scoped objects:
    - Allows ADMIN (and superusers) unrestricted access.
    - For SURVEYOR: checks that the object's claim is assigned to request.user
      via a SurveyAssignment.
    Checks has_object_permission to block surveyors from accessing unassigned claims by ID.
    """

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        user = request.user
        if not user or not user.is_authenticated:
            return False

        if user.role == 'ADMIN' or user.is_superuser:
            return True

        if user.role == 'SURVEYOR':
            claim = None
            if isinstance(obj, Claim):
                claim = obj
            elif hasattr(obj, 'claim'):
                claim = obj.claim
            elif hasattr(obj, 'inspection') and hasattr(obj.inspection, 'claim'):
                claim = obj.inspection.claim

            if claim is not None:
                return claim.assignments.filter(surveyor=user).exclude(status="REASSIGNED").exists()

        return False


def filter_claim_scoped_queryset(queryset, user, claim_lookup='claim'):
    """
    Filters a queryset based on user role:
    - Admins & Superusers: unrestricted queryset.
    - Surveyors: only records where claim has a non-reassigned SurveyAssignment for user.
    - Others: empty queryset.
    """
    if not user or not user.is_authenticated:
        return queryset.none()
    if getattr(user, 'role', None) == 'ADMIN' or user.is_superuser:
        return queryset
    if getattr(user, 'role', None) == 'SURVEYOR':
        valid_assignments = SurveyAssignment.objects.filter(surveyor=user).exclude(status="REASSIGNED")
        if claim_lookup == 'self':
            return queryset.filter(assignments__in=valid_assignments).distinct()
        else:
            return queryset.filter(**{f"{claim_lookup}__assignments__in": valid_assignments}).distinct()
    return queryset.none()


class ClaimScopedQuerySetMixin:
    """Mixin for DRF ViewSets to scope querysets and apply IsAssignedSurveyorOrAdmin."""
    permission_classes = [IsAssignedSurveyorOrAdmin]
    claim_lookup_field = 'claim'

    def get_queryset(self):
        qs = super().get_queryset()
        lookup = getattr(self, 'claim_lookup_field', 'claim')
        return filter_claim_scoped_queryset(qs, self.request.user, lookup)
