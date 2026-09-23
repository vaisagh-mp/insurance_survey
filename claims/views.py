from django.core.exceptions import ValidationError
from django.db import transaction
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.permissions import (
    IsAdminRole,
    IsAssignedSurveyorOrAdmin,
    ClaimScopedQuerySetMixin
)
from .models import Claim, Insurer, Insured, Policy, SurveyAssignment, ClaimStatus, Priority
from .services import (
    transition_claim_status,
    assign_surveyor,
    reassign_surveyor,
    submit_report,
    raise_query,
    respond_query,
    close_claim,
)
from .serializers import (
    InsurerSerializer,
    InsuredSerializer,
    PolicySerializer,
    SurveyAssignmentSerializer,
    AssignSurveyorSerializer,
    ReassignSurveyorSerializer,
    ClaimStatusActionSerializer,
    ClaimSerializer,
)
from surveys.models import Inspection
from surveys.serializers import InspectionSerializer
from documents.models import ClaimDocument, Requirement
from documents.serializers import ClaimDocumentSerializer, RequirementSerializer
from assessments.models import Assessment
from assessments.serializers import AssessmentSerializer
from assessments.services import recalculate_assessment
from reports.models import ILA, ISR, FSR
from reports.serializers import ILASerializer, ISRSerializer, FSRSerializer


class InsurerViewSet(viewsets.ModelViewSet):
    queryset = Insurer.objects.all()
    serializer_class = InsurerSerializer

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminRole()]
        return [IsAuthenticated()]


class InsuredViewSet(viewsets.ModelViewSet):
    queryset = Insured.objects.all()
    serializer_class = InsuredSerializer

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminRole()]
        return [IsAuthenticated()]


class PolicyViewSet(viewsets.ModelViewSet):
    queryset = Policy.objects.all()
    serializer_class = PolicySerializer

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminRole()]
        return [IsAuthenticated()]


class ClaimViewSet(ClaimScopedQuerySetMixin, viewsets.ModelViewSet):
    """
    API endpoint for viewing and managing claims.
    Enforces claim-scoped access:
    - Admins see all claims.
    - Surveyors see and access only claims assigned to them.
    """
    queryset = Claim.objects.all()
    serializer_class = ClaimSerializer
    permission_classes = [IsAssignedSurveyorOrAdmin]
    claim_lookup_field = 'self'

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @extend_schema(
        request=AssignSurveyorSerializer,
        responses={200: SurveyAssignmentSerializer, 201: SurveyAssignmentSerializer}
    )
    @action(detail=True, methods=['post'], url_path='assign-surveyor')
    def assign_surveyor(self, request, pk=None):
        claim = self.get_object()
        if not (request.user.is_admin_role or request.user.is_superuser):
            return Response(
                {'detail': 'Only administrators can assign surveyors.'},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = AssignSurveyorSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            assignment = assign_surveyor(
                claim=claim,
                surveyor=serializer.validated_data['surveyor'],
                assigned_by=request.user,
                due_date=serializer.validated_data.get('due_date'),
                instructions=serializer.validated_data.get('instructions', ''),
                priority=serializer.validated_data.get('priority', Priority.MEDIUM),
                request=request
            )
            return Response(SurveyAssignmentSerializer(assignment).data, status=status.HTTP_201_CREATED)
        except ValidationError as e:
            return Response(
                {'detail': e.messages if hasattr(e, 'messages') else str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @extend_schema(
        request=ReassignSurveyorSerializer,
        responses={200: SurveyAssignmentSerializer}
    )
    @action(detail=True, methods=['post'], url_path='reassign-surveyor')
    def reassign_surveyor(self, request, pk=None):
        claim = self.get_object()
        if not (request.user.is_admin_role or request.user.is_superuser):
            return Response(
                {'detail': 'Only administrators can reassign surveyors.'},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = ReassignSurveyorSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            assignment = reassign_surveyor(
                claim=claim,
                new_surveyor=serializer.validated_data['surveyor'],
                assigned_by=request.user,
                due_date=serializer.validated_data.get('due_date'),
                instructions=serializer.validated_data.get('instructions', ''),
                priority=serializer.validated_data.get('priority', Priority.MEDIUM),
                remarks=serializer.validated_data.get('remarks', ''),
                request=request
            )
            return Response(SurveyAssignmentSerializer(assignment).data, status=status.HTTP_200_OK)
        except ValidationError as e:
            return Response(
                {'detail': e.messages if hasattr(e, 'messages') else str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    # Sub-resource: Inspections
    @extend_schema(
        methods=['get'],
        responses={200: InspectionSerializer(many=True)}
    )
    @extend_schema(
        methods=['post'],
        request=InspectionSerializer,
        responses={201: InspectionSerializer}
    )
    @action(detail=True, methods=['get', 'post'], url_path='inspections')
    def inspections(self, request, pk=None):
        claim = self.get_object()
        if request.method == 'GET':
            inspections = claim.inspections.all()
            serializer = InspectionSerializer(inspections, many=True)
            return Response(serializer.data)
        elif request.method == 'POST':
            serializer = InspectionSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            surveyor = serializer.validated_data.get('surveyor') or request.user
            inspection = serializer.save(claim=claim, surveyor=surveyor)
            return Response(InspectionSerializer(inspection).data, status=status.HTTP_201_CREATED)

    # Sub-resource: Documents
    @extend_schema(
        methods=['get'],
        responses={200: ClaimDocumentSerializer(many=True)}
    )
    @extend_schema(
        methods=['post'],
        request=ClaimDocumentSerializer,
        responses={201: ClaimDocumentSerializer}
    )
    @action(detail=True, methods=['get', 'post'], url_path='documents')
    def documents(self, request, pk=None):
        claim = self.get_object()
        if request.method == 'GET':
            documents = claim.documents.all()
            serializer = ClaimDocumentSerializer(documents, many=True)
            return Response(serializer.data)
        elif request.method == 'POST':
            serializer = ClaimDocumentSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            doc = serializer.save(claim=claim, uploaded_by=request.user)
            return Response(ClaimDocumentSerializer(doc).data, status=status.HTTP_201_CREATED)

    # Sub-resource: Requirements
    @extend_schema(
        methods=['get'],
        responses={200: RequirementSerializer(many=True)}
    )
    @extend_schema(
        methods=['post'],
        request=RequirementSerializer,
        responses={201: RequirementSerializer}
    )
    @action(detail=True, methods=['get', 'post'], url_path='requirements')
    def requirements(self, request, pk=None):
        claim = self.get_object()
        if request.method == 'GET':
            reqs = claim.requirements.all()
            serializer = RequirementSerializer(reqs, many=True)
            return Response(serializer.data)
        elif request.method == 'POST':
            serializer = RequirementSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            req = serializer.save(claim=claim, created_by=request.user)
            return Response(RequirementSerializer(req).data, status=status.HTTP_201_CREATED)

    # Sub-resource: Assessment
    @extend_schema(
        methods=['get'],
        responses={200: AssessmentSerializer}
    )
    @extend_schema(
        methods=['post'],
        request=AssessmentSerializer,
        responses={201: AssessmentSerializer}
    )
    @extend_schema(
        methods=['patch'],
        request=AssessmentSerializer,
        responses={200: AssessmentSerializer}
    )
    @action(detail=True, methods=['get', 'post', 'patch'], url_path='assessment')
    def assessment(self, request, pk=None):
        claim = self.get_object()
        if request.method == 'GET':
            if not hasattr(claim, 'assessment'):
                return Response({'detail': 'No assessment created for this claim.'}, status=status.HTTP_404_NOT_FOUND)
            serializer = AssessmentSerializer(claim.assessment)
            return Response(serializer.data)
        elif request.method == 'POST':
            if hasattr(claim, 'assessment'):
                return Response({'detail': 'Assessment already exists for this claim. Use PATCH to update.'}, status=status.HTTP_400_BAD_REQUEST)
            serializer = AssessmentSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            assessment = serializer.save(claim=claim, created_by=request.user)
            return Response(AssessmentSerializer(assessment).data, status=status.HTTP_201_CREATED)
        elif request.method == 'PATCH':
            if not hasattr(claim, 'assessment'):
                return Response({'detail': 'No assessment exists to update. Use POST to create.'}, status=status.HTTP_404_NOT_FOUND)
            serializer = AssessmentSerializer(claim.assessment, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            assessment = serializer.save()
            return Response(AssessmentSerializer(assessment).data, status=status.HTTP_200_OK)

    # Sub-resource: ILA
    @extend_schema(
        methods=['get'],
        responses={200: ILASerializer(many=True)}
    )
    @extend_schema(
        methods=['post'],
        request=ILASerializer,
        responses={201: ILASerializer}
    )
    @action(detail=True, methods=['get', 'post'], url_path='ila')
    def ila(self, request, pk=None):
        claim = self.get_object()
        if request.method == 'GET':
            reports = claim.ila_reports.all()
            return Response(ILASerializer(reports, many=True).data)
        elif request.method == 'POST':
            serializer = ILASerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            surveyor = serializer.validated_data.get('surveyor') or request.user
            report = serializer.save(claim=claim, prepared_by=request.user, surveyor=surveyor)
            return Response(ILASerializer(report).data, status=status.HTTP_201_CREATED)

    # Sub-resource: ISR
    @extend_schema(
        methods=['get'],
        responses={200: ISRSerializer(many=True)}
    )
    @extend_schema(
        methods=['post'],
        request=ISRSerializer,
        responses={201: ISRSerializer}
    )
    @action(detail=True, methods=['get', 'post'], url_path='isr')
    def isr(self, request, pk=None):
        claim = self.get_object()
        if request.method == 'GET':
            reports = claim.isr_reports.all()
            return Response(ISRSerializer(reports, many=True).data)
        elif request.method == 'POST':
            serializer = ISRSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            report = serializer.save(claim=claim, prepared_by=request.user)
            return Response(ISRSerializer(report).data, status=status.HTTP_201_CREATED)

    # Sub-resource: FSR
    @extend_schema(
        methods=['get'],
        responses={200: FSRSerializer(many=True)}
    )
    @extend_schema(
        methods=['post'],
        request=FSRSerializer,
        responses={201: FSRSerializer}
    )
    @action(detail=True, methods=['get', 'post'], url_path='fsr')
    def fsr(self, request, pk=None):
        claim = self.get_object()
        if request.method == 'GET':
            reports = claim.fsr_reports.all()
            return Response(FSRSerializer(reports, many=True).data)
        elif request.method == 'POST':
            serializer = FSRSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            report = serializer.save(claim=claim, prepared_by=request.user)
            return Response(FSRSerializer(report).data, status=status.HTTP_201_CREATED)

    # Status Transition Actions via service functions
    @extend_schema(request=ClaimStatusActionSerializer, responses={200: ClaimSerializer})
    @action(detail=True, methods=['post'], url_path='submit-report')
    def submit_report(self, request, pk=None):
        claim = self.get_object()
        try:
            submit_report(claim=claim, report=None, submitted_by=request.user, request=request)
            claim.refresh_from_db()
            return Response(ClaimSerializer(claim).data, status=status.HTTP_200_OK)
        except ValidationError as e:
            return Response(
                {'detail': e.messages if hasattr(e, 'messages') else str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @extend_schema(request=ClaimStatusActionSerializer, responses={200: ClaimSerializer})
    @action(detail=True, methods=['post'], url_path='raise-query')
    def raise_query(self, request, pk=None):
        claim = self.get_object()
        serializer = ClaimStatusActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        remarks = serializer.validated_data.get('remarks', '')
        try:
            raise_query(claim=claim, raised_by=request.user, remarks=remarks, request=request)
            claim.refresh_from_db()
            return Response(ClaimSerializer(claim).data, status=status.HTTP_200_OK)
        except ValidationError as e:
            return Response(
                {'detail': e.messages if hasattr(e, 'messages') else str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @extend_schema(request=ClaimStatusActionSerializer, responses={200: ClaimSerializer})
    @action(detail=True, methods=['post'], url_path='respond-query')
    def respond_query(self, request, pk=None):
        claim = self.get_object()
        serializer = ClaimStatusActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        remarks = serializer.validated_data.get('remarks', '')
        try:
            respond_query(claim=claim, report=None, responded_by=request.user, remarks=remarks, request=request)
            claim.refresh_from_db()
            return Response(ClaimSerializer(claim).data, status=status.HTTP_200_OK)
        except ValidationError as e:
            return Response(
                {'detail': e.messages if hasattr(e, 'messages') else str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @extend_schema(request=ClaimStatusActionSerializer, responses={200: ClaimSerializer})
    @action(detail=True, methods=['post'], url_path='close')
    def close(self, request, pk=None):
        claim = self.get_object()
        serializer = ClaimStatusActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        remarks = serializer.validated_data.get('remarks', '')
        try:
            close_claim(claim=claim, closed_by=request.user, remarks=remarks, request=request)
            claim.refresh_from_db()
            return Response(ClaimSerializer(claim).data, status=status.HTTP_200_OK)
        except ValidationError as e:
            return Response(
                {'detail': e.messages if hasattr(e, 'messages') else str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
