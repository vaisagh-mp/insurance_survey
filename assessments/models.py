from decimal import Decimal
from django.conf import settings
from django.db import models
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from documents.validators import validate_document_extension, validate_file_size


class Invoice(models.Model):
    claim = models.ForeignKey(
        'claims.Claim',
        on_delete=models.CASCADE,
        related_name='invoices'
    )
    invoice_number = models.CharField(max_length=100)
    invoice_date = models.DateField()
    vendor_name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    total_amount = models.DecimalField(max_digits=15, decimal_places=2)
    document = models.FileField(
        upload_to="invoices/%Y/%m/",
        null=True,
        blank=True,
        validators=[validate_document_extension, validate_file_size]
    )
    verified = models.BooleanField(default=False)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='verified_invoices'
    )
    remarks = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'nis_invoice'
        ordering = ['-invoice_date', '-created_at']
        verbose_name = 'Invoice'
        verbose_name_plural = 'Invoices'

    def save(self, *args, **kwargs):
        if self.total_amount is None:
            self.total_amount = (self.amount or Decimal('0.00')) + (self.tax_amount or Decimal('0.00'))
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Invoice {self.invoice_number} - {self.vendor_name} ({self.claim.claim_number})"


class Assessment(models.Model):
    claim = models.OneToOneField(
        'claims.Claim',
        on_delete=models.CASCADE,
        related_name='assessment'
    )
    gross_assessed_loss = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        editable=False
    )
    salvage_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00')
    )
    underinsurance_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Percentage of underinsurance e.g. 10.5 for 10.5%"
    )
    underinsurance_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        editable=False
    )
    adjusted_loss = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        editable=False
    )
    depreciation_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00')
    )
    policy_excess = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00')
    )
    other_deductions = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00')
    )
    net_assessed_loss = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        editable=False
    )
    assessment_remarks = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='assessments_created'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'nis_assessment'
        ordering = ['-created_at']
        verbose_name = 'Assessment'
        verbose_name_plural = 'Assessments'

    def __str__(self):
        return f"Assessment for Claim {self.claim.claim_number}: Net Rs. {self.net_assessed_loss}"


class AssessmentItem(models.Model):
    assessment = models.ForeignKey(
        Assessment,
        on_delete=models.CASCADE,
        related_name='items'
    )
    item_code = models.CharField(max_length=50, blank=True)
    description = models.TextField()
    specification = models.TextField(blank=True)
    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    rate = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    category = models.CharField(max_length=100, blank=True)
    claimed_amount = models.DecimalField(max_digits=15, decimal_places=2)
    assessed_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00')
    )
    remarks = models.TextField(blank=True)

    class Meta:
        db_table = 'nis_assessment_item'
        ordering = ['id']
        verbose_name = 'Assessment Item'
        verbose_name_plural = 'Assessment Items'

    def clean(self):
        super().clean()
        if self.quantity is not None and self.quantity < Decimal('0.00'):
            raise ValidationError({'quantity': 'Quantity cannot be negative.'})
        if self.rate is not None and self.rate < Decimal('0.00'):
            raise ValidationError({'rate': 'Rate cannot be negative.'})

    def save(self, *args, **kwargs):
        if self.quantity is not None and self.rate is not None:
            self.assessed_amount = (self.quantity * self.rate).quantize(Decimal('0.01'))
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Item: {self.description[:40]} ({self.quantity} @ {self.rate})"
