from decimal import Decimal, ROUND_HALF_UP
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


def round_curr(val):
    if val is None:
        return Decimal('0.00')
    return Decimal(str(val)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


class ServiceInvoice(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft'
        SENT = 'SENT', 'Sent'
        PAID = 'PAID', 'Paid'
        CANCELLED = 'CANCELLED', 'Cancelled'

    claim = models.ForeignKey(
        'claims.Claim',
        on_delete=models.CASCADE,
        related_name='service_invoices'
    )
    invoice_number = models.CharField(max_length=50, unique=True, blank=True)
    invoice_date = models.DateField(default=timezone.localdate)
    due_date = models.DateField()
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT
    )
    sent_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    payment_reference = models.CharField(max_length=100, blank=True)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    tax_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('18.00'))
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    notes = models.TextField(blank=True, help_text="Notes printed on invoice PDF (e.g. Bank details)")
    remarks = models.TextField(blank=True, help_text="Internal notes only — never printed on PDF")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='service_invoices_created'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'nis_service_invoice'
        ordering = ['-invoice_date', '-created_at']
        verbose_name = 'Service Invoice'
        verbose_name_plural = 'Service Invoices'

    def clean(self):
        super().clean()
        if self.claim_id and self.status != self.Status.CANCELLED:
            qs = ServiceInvoice.objects.filter(claim_id=self.claim_id).exclude(status=self.Status.CANCELLED)
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if qs.exists():
                raise ValidationError("A non-cancelled service invoice already exists for this claim.")

    @property
    def is_overdue(self):
        """Derived property: true if sent and past due date."""
        if self.status == self.Status.SENT and self.due_date:
            today = timezone.localdate() if hasattr(timezone, 'localdate') else timezone.now().date()
            return self.due_date < today
        return False

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            last_inv = ServiceInvoice.objects.order_by('-id').first()
            next_id = (last_inv.id + 1) if last_inv and last_inv.id else 1
            candidate = f"SINV-{next_id:05d}"
            while ServiceInvoice.objects.filter(invoice_number=candidate).exists():
                next_id += 1
                candidate = f"SINV-{next_id:05d}"
            self.invoice_number = candidate
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.invoice_number} ({self.claim.claim_number}) - {self.get_status_display()}"


class ServiceInvoiceItem(models.Model):
    invoice = models.ForeignKey(
        ServiceInvoice,
        on_delete=models.CASCADE,
        related_name='items'
    )
    description = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('1.00'))
    rate = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'nis_service_invoice_item'
        ordering = ['id']
        verbose_name = 'Service Invoice Item'
        verbose_name_plural = 'Service Invoice Items'

    def save(self, *args, **kwargs):
        qty = Decimal(str(self.quantity or 0))
        rate = Decimal(str(self.rate or 0))
        self.amount = round_curr(qty * rate)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.description} - {self.amount}"
