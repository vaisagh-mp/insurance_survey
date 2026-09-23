from rest_framework import viewsets
from accounts.permissions import (
    IsAssignedSurveyorOrAdmin,
    ClaimScopedQuerySetMixin,
)
from .models import ClaimDocument, Requirement
from .serializers import ClaimDocumentSerializer, RequirementSerializer


class ClaimDocumentViewSet(ClaimScopedQuerySetMixin, viewsets.ModelViewSet):
    """
    API endpoint for viewing, downloading, and deleting claim documents.
    Claim-scoped: accessible only by assigned surveyors or admins.
    Verification requires Administrator privileges.
    """
    queryset = ClaimDocument.objects.all()
    serializer_class = ClaimDocumentSerializer
    permission_classes = [IsAssignedSurveyorOrAdmin]
    claim_lookup_field = 'claim'

    def perform_update(self, serializer):
        if 'verified' in serializer.validated_data:
            user = self.request.user
            if getattr(user, 'role', None) != 'ADMIN' and not user.is_superuser:
                from rest_framework.exceptions import PermissionDenied as DRFPermissionDenied
                raise DRFPermissionDenied("To change verification status, the logged-in user must be an Administrator.")
            if serializer.validated_data['verified'] and not serializer.instance.verified:
                from django.utils import timezone
                serializer.save(verified_by=user, verified_at=timezone.now())
                return
        serializer.save()


class RequirementViewSet(ClaimScopedQuerySetMixin, viewsets.ModelViewSet):
    """
    API endpoint for viewing, creating, and updating (PATCH) document requirements (LOR items).
    Claim-scoped: accessible only by assigned surveyors or admins.
    Verification requires Administrator privileges.
    """
    queryset = Requirement.objects.all()
    serializer_class = RequirementSerializer
    permission_classes = [IsAssignedSurveyorOrAdmin]
    claim_lookup_field = 'claim'

    def perform_update(self, serializer):
        if 'status' in serializer.validated_data:
            new_status = serializer.validated_data['status']
            instance = self.get_object()
            if new_status == Requirement.Status.VERIFIED or instance.status == Requirement.Status.VERIFIED:
                user = self.request.user
                if getattr(user, 'role', None) != 'ADMIN' and not user.is_superuser:
                    from rest_framework.exceptions import PermissionDenied as DRFPermissionDenied
                    raise DRFPermissionDenied("To change verification status, the logged-in user must be an Administrator.")
        serializer.save()


def secure_media_view(request, path):
    """
    Secure file-serving view for sensitive insurance documents, photos, and invoices.
    Enforces authentication and role-based access to the owning claim:
    - Admin / Superuser: full access.
    - Surveyor: accessible only if actively assigned to the owning claim (excluding REASSIGNED).
    - Other / unassigned: PermissionDenied (403).
    - Unauthenticated: redirects to login.
    Streams file via the matched model instance's own file field (.open('rb')).
    """
    import mimetypes
    from django.http import FileResponse, Http404
    from django.core.exceptions import PermissionDenied
    from django.shortcuts import redirect
    from django.contrib.auth import get_user_model
    from surveys.models import InspectionPhoto
    from assessments.models import Invoice
    from claims.models import SurveyAssignment

    User = get_user_model()

    if not request.user.is_authenticated:
        return redirect(f'/login/?next={request.path}')

    clean_path = path.lstrip('/')
    if clean_path.startswith('media/'):
        clean_path = clean_path[len('media/'):]

    claim = None
    file_field = None
    filename = None

    # 1. Check ClaimDocument
    doc = ClaimDocument.objects.filter(file=clean_path).select_related('claim').first()
    if doc:
        claim = doc.claim
        file_field = doc.file
        filename = doc.file.name.split('/')[-1]

    # 2. Check InspectionPhoto
    photo = None
    if not doc:
        photo = InspectionPhoto.objects.filter(image=clean_path).select_related('inspection__claim').first()
        if photo and photo.inspection:
            claim = photo.inspection.claim
            file_field = photo.image
            filename = photo.image.name.split('/')[-1]

    # 3. Check Invoice
    invoice = None
    if not doc and not photo:
        invoice = Invoice.objects.filter(document=clean_path).select_related('claim').first()
        if invoice:
            claim = invoice.claim
            file_field = invoice.document
            filename = invoice.document.name.split('/')[-1]

    # Fallback to endswith matching if exact match not found
    if not file_field:
        doc = ClaimDocument.objects.filter(file__endswith=clean_path).select_related('claim').first()
        if doc:
            claim = doc.claim
            file_field = doc.file
            filename = doc.file.name.split('/')[-1]
        else:
            photo = InspectionPhoto.objects.filter(image__endswith=clean_path).select_related('inspection__claim').first()
            if photo and photo.inspection:
                claim = photo.inspection.claim
                file_field = photo.image
                filename = photo.image.name.split('/')[-1]
            else:
                invoice = Invoice.objects.filter(document__endswith=clean_path).select_related('claim').first()
                if invoice:
                    claim = invoice.claim
                    file_field = invoice.document
                    filename = invoice.document.name.split('/')[-1]

    if not file_field or not claim:
        raise Http404("File not found or not associated with a claim.")

    # Permission check (Step 10 rules)
    is_admin = (request.user.role == User.Role.ADMIN) or request.user.is_superuser
    if is_admin:
        has_access = True
    elif request.user.role == User.Role.SURVEYOR:
        has_access = claim.assignments.filter(
            surveyor=request.user
        ).exclude(status=SurveyAssignment.Status.REASSIGNED).exists()
    else:
        has_access = False

    if not has_access:
        raise PermissionDenied("You do not have permission to access this file.")

    try:
        f = file_field.open('rb')
    except Exception:
        raise Http404("File could not be opened from storage.")

    content_type, _ = mimetypes.guess_type(filename)
    if not content_type:
        content_type = 'application/octet-stream'

    response = FileResponse(f, content_type=content_type)
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    return response
