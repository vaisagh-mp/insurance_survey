from django.conf import settings
from django.db import models
from .validators import validate_document_extension, validate_file_size


class DocumentType(models.Model):
    name = models.CharField(max_length=150)
    code = models.CharField(max_length=50, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'nis_document_type'
        ordering = ['name']
        verbose_name = 'Document Type'
        verbose_name_plural = 'Document Types'

    def __str__(self):
        return f"{self.name} ({self.code})"


class ClaimDocument(models.Model):
    claim = models.ForeignKey(
        'claims.Claim',
        on_delete=models.CASCADE,
        related_name='documents'
    )
    document_type = models.ForeignKey(
        DocumentType,
        on_delete=models.PROTECT,
        related_name='claim_documents'
    )
    file = models.FileField(
        upload_to="claim_documents/%Y/%m/",
        validators=[validate_document_extension, validate_file_size]
    )
    document_number = models.CharField(max_length=100, blank=True)
    document_date = models.DateField(null=True, blank=True)
    description = models.TextField(blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='uploaded_documents'
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    verified = models.BooleanField(default=False)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='verified_documents'
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    remarks = models.TextField(blank=True)

    class Meta:
        db_table = 'nis_claim_document'
        ordering = ['-uploaded_at']
        verbose_name = 'Claim Document'
        verbose_name_plural = 'Claim Documents'

    def __str__(self):
        doc_no = f" #{self.document_number}" if self.document_number else ""
        return f"{self.document_type.name}{doc_no} ({self.claim.claim_number})"


class Requirement(models.Model):
    class RequestedFrom(models.TextChoices):
        INSURED = 'INSURED', 'Insured'
        INSURER = 'INSURER', 'Insurer'
        OTHER = 'OTHER', 'Other'

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        PARTIALLY_RECEIVED = 'PARTIALLY_RECEIVED', 'Partially Received'
        RECEIVED = 'RECEIVED', 'Received'
        VERIFIED = 'VERIFIED', 'Verified'
        REJECTED = 'REJECTED', 'Rejected'

    claim = models.ForeignKey(
        'claims.Claim',
        on_delete=models.CASCADE,
        related_name='requirements'
    )
    description = models.TextField()
    requested_from = models.CharField(
        max_length=20,
        choices=RequestedFrom.choices,
        default=RequestedFrom.INSURED
    )
    requested_date = models.DateField()
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.PENDING
    )
    received_date = models.DateField(null=True, blank=True)
    related_document = models.ForeignKey(
        ClaimDocument,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='requirements'
    )
    remarks = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='created_requirements'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'nis_requirement'
        ordering = ['-requested_date', '-created_at']
        verbose_name = 'Requirement (LOR Item)'
        verbose_name_plural = 'Requirements (LOR Items)'

    def __str__(self):
        return f"LOR Item: {self.description[:40]}... ({self.claim.claim_number}) - {self.get_status_display()}"
