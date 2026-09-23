from django.http import HttpResponse
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema
from drf_spectacular.types import OpenApiTypes

from accounts.permissions import (
    IsAssignedSurveyorOrAdmin,
    ClaimScopedQuerySetMixin,
)
from documents.serializers import ClaimDocumentSerializer
from .models import ILA, ISR, FSR
from .serializers import ILASerializer, ISRSerializer, FSRSerializer
from .services import generate_report_pdf, save_report_pdf_as_document


class ReportPdfActionsMixin:
    """Mixin providing preview-pdf and generate-pdf actions for report viewsets."""

    @extend_schema(
        methods=['get'],
        summary="Preview report PDF",
        description="Renders and streams the report PDF inline for preview in a browser tab.",
        responses={(200, 'application/pdf'): OpenApiTypes.BINARY}
    )
    @action(detail=True, methods=['get'], url_path='preview-pdf')
    def preview_pdf(self, request, pk=None):
        report = self.get_object()
        pdf_bytes = generate_report_pdf(report)
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="{report.report_number}.pdf"'
        return response

    @extend_schema(
        methods=['post'],
        summary="Generate and save report PDF",
        description="Renders the report PDF and saves it as a new ClaimDocument linked to the claim.",
        responses={201: ClaimDocumentSerializer}
    )
    @action(detail=True, methods=['post'], url_path='generate-pdf')
    def generate_pdf(self, request, pk=None):
        report = self.get_object()
        claim_doc = save_report_pdf_as_document(report, request.user)
        return Response(ClaimDocumentSerializer(claim_doc).data, status=status.HTTP_201_CREATED)


class ILAViewSet(ClaimScopedQuerySetMixin, ReportPdfActionsMixin, viewsets.ModelViewSet):
    """
    API endpoint for Immediate Loss Advice (ILA) reports.
    Claim-scoped: accessible only by assigned surveyors or admins.
    """
    queryset = ILA.objects.all()
    serializer_class = ILASerializer
    permission_classes = [IsAssignedSurveyorOrAdmin]
    claim_lookup_field = 'claim'

    def perform_create(self, serializer):
        serializer.save(prepared_by=self.request.user)


class ISRViewSet(ClaimScopedQuerySetMixin, ReportPdfActionsMixin, viewsets.ModelViewSet):
    """
    API endpoint for Initial / Interim Survey Reports (ISR).
    Claim-scoped: accessible only by assigned surveyors or admins.
    """
    queryset = ISR.objects.all()
    serializer_class = ISRSerializer
    permission_classes = [IsAssignedSurveyorOrAdmin]
    claim_lookup_field = 'claim'

    def perform_create(self, serializer):
        serializer.save(prepared_by=self.request.user)


class FSRViewSet(ClaimScopedQuerySetMixin, ReportPdfActionsMixin, viewsets.ModelViewSet):
    """
    API endpoint for Final Survey Reports (FSR).
    Claim-scoped: accessible only by assigned surveyors or admins.
    """
    queryset = FSR.objects.all()
    serializer_class = FSRSerializer
    permission_classes = [IsAssignedSurveyorOrAdmin]
    claim_lookup_field = 'claim'

    def perform_create(self, serializer):
        serializer.save(prepared_by=self.request.user)
