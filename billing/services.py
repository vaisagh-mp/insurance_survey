from decimal import Decimal
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone
from .models import ServiceInvoice, ServiceInvoiceItem, round_curr


@transaction.atomic
def recalculate_invoice(invoice):
    """
    Recalculates all financial figures for a ServiceInvoice:
    - amount per ServiceInvoiceItem = quantity * rate (recompute and save each item first).
    - subtotal = sum of ServiceInvoiceItem.amount.
    - tax_amount = subtotal * (tax_percentage / 100).
    - total_amount = subtotal + tax_amount.
    - Persists the invoice atomically.
    """
    # 1. Recompute and save each item's amount
    for item in invoice.items.select_for_update():
        qty = Decimal(str(item.quantity or 0))
        rate = Decimal(str(item.rate or 0))
        item.amount = round_curr(qty * rate)
        item.save(update_fields=['amount'])

    # 2. Subtotal = sum of item amounts
    subtotal = sum(
        (item.amount for item in invoice.items.all()),
        Decimal('0.00')
    )
    invoice.subtotal = round_curr(subtotal)

    # 3. Tax Amount
    tax_pct = Decimal(str(invoice.tax_percentage or 0))
    if tax_pct > Decimal('0.00'):
        tax_amt = (invoice.subtotal * tax_pct) / Decimal('100.00')
        invoice.tax_amount = round_curr(tax_amt)
    else:
        invoice.tax_amount = Decimal('0.00')

    # 4. Total Amount
    invoice.total_amount = round_curr(invoice.subtotal + invoice.tax_amount)

    # 5. Save the invoice
    invoice.save(update_fields=['subtotal', 'tax_amount', 'total_amount', 'updated_at'])

    return invoice


def add_invoice_item(invoice, description, quantity=Decimal('1.00'), rate=Decimal('0.00')):
    """
    Adds a line item to the invoice and immediately recalculates the invoice.
    Locked: Only allowed if invoice is in DRAFT status.
    """
    if invoice.status != ServiceInvoice.Status.DRAFT:
        raise ValidationError(
            f"Cannot add item. Invoice #{invoice.invoice_number} is in '{invoice.status}' status and is locked."
        )

    item = ServiceInvoiceItem.objects.create(
        invoice=invoice,
        description=description,
        quantity=quantity,
        rate=rate
    )
    recalculate_invoice(invoice)
    return item


def update_invoice_item(item, description=None, quantity=None, rate=None):
    """
    Updates a line item on the invoice and immediately recalculates the invoice.
    Locked: Only allowed if invoice is in DRAFT status.
    """
    if item.invoice.status != ServiceInvoice.Status.DRAFT:
        raise ValidationError(
            f"Cannot update item. Invoice #{item.invoice.invoice_number} is in '{item.invoice.status}' status and is locked."
        )

    if description is not None:
        item.description = description
    if quantity is not None:
        item.quantity = Decimal(str(quantity))
    if rate is not None:
        item.rate = Decimal(str(rate))

    item.save()
    recalculate_invoice(item.invoice)
    return item


def delete_invoice_item(item):
    """
    Deletes a line item and immediately recalculates the invoice.
    Locked: Only allowed if invoice is in DRAFT status.
    """
    invoice = item.invoice
    if invoice.status != ServiceInvoice.Status.DRAFT:
        raise ValidationError(
            f"Cannot delete item. Invoice #{invoice.invoice_number} is in '{invoice.status}' status and is locked."
        )

    item.delete()
    recalculate_invoice(invoice)
    return invoice


@transaction.atomic
def mark_invoice_sent(invoice, user=None):
    """
    Transitions invoice status from DRAFT to SENT.
    Fails if invoice is not in DRAFT status.
    """
    if invoice.status != ServiceInvoice.Status.DRAFT:
        raise ValidationError(
            f"Cannot send invoice with status '{invoice.status}'. Only DRAFT invoices can be marked as sent."
        )

    invoice.status = ServiceInvoice.Status.SENT
    invoice.sent_at = timezone.now()
    invoice.save(update_fields=['status', 'sent_at', 'updated_at'])
    return invoice


@transaction.atomic
def record_invoice_payment(invoice, user=None, payment_reference=''):
    """
    Transitions invoice status from SENT to PAID.
    Fails if invoice is not in SENT status.
    """
    if invoice.status != ServiceInvoice.Status.SENT:
        raise ValidationError(
            f"Cannot record payment for invoice with status '{invoice.status}'. Only SENT invoices can be marked as paid."
        )

    invoice.status = ServiceInvoice.Status.PAID
    invoice.paid_at = timezone.now()
    invoice.payment_reference = payment_reference.strip() if payment_reference else ''
    invoice.save(update_fields=['status', 'paid_at', 'payment_reference', 'updated_at'])
    return invoice


@transaction.atomic
def cancel_invoice(invoice, user=None, reason=''):
    """
    Transitions invoice status to CANCELLED.
    Requires a non-blank cancellation reason.
    Only DRAFT or SENT invoices can be cancelled (PAID or already CANCELLED cannot).
    Appends the cancellation reason into the invoice's remarks field.
    """
    if not reason or not reason.strip():
        raise ValidationError("A non-blank cancellation reason is required.")

    if invoice.status not in [ServiceInvoice.Status.DRAFT, ServiceInvoice.Status.SENT]:
        raise ValidationError(
            f"Cannot cancel invoice with status '{invoice.status}'. Only DRAFT or SENT invoices can be cancelled."
        )

    now_str = timezone.now().strftime('%Y-%m-%d %H:%M')
    user_display = (user.get_full_name() or user.username) if user else "System"
    cancel_entry = f"Cancelled by {user_display} on {now_str}: {reason.strip()}"

    if invoice.remarks:
        invoice.remarks = f"{invoice.remarks}\n{cancel_entry}"
    else:
        invoice.remarks = cancel_entry

    invoice.status = ServiceInvoice.Status.CANCELLED
    invoice.save(update_fields=['status', 'remarks', 'updated_at'])
    return invoice


def generate_invoice_pdf(invoice):
    """
    Render fee invoice template with WeasyPrint and return raw PDF bytes.
    """
    import weasyprint
    from reports.services import get_soteria_assets

    assets = get_soteria_assets()
    firm_name = getattr(settings, 'FIRM_NAME', 'SOTERIA Insurance Surveyors & Loss Assessors Pvt. Ltd.')
    firm_address = getattr(settings, 'FIRM_ADDRESS', '')
    firm_gstin = getattr(settings, 'FIRM_GSTIN', '')

    context = {
        'invoice': invoice,
        'claim': invoice.claim,
        'items': invoice.items.all().order_by('id'),
        'firm_name': firm_name,
        'firm_address': firm_address,
        'firm_gstin': firm_gstin,
        'insurer': invoice.claim.insurer,
        'soteria_logo': assets.get('logo', ''),
        'soteria_swoosh': assets.get('swoosh', ''),
        'soteria_footer_swoosh': assets.get('footer_swoosh', ''),
        'soteria_stamp': assets.get('stamp', ''),
        'soteria_signature': assets.get('signature', ''),
    }
    html_string = render_to_string('billing/service_invoice_pdf.html', context)
    pdf_bytes = weasyprint.HTML(string=html_string).write_pdf()
    return pdf_bytes
