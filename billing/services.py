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


def format_inr(val):
    if val is None:
        return "0.00"
    val = Decimal(str(val)).quantize(Decimal('0.01'))
    s = f"{val:.2f}"
    parts = s.split('.')
    integer_part = parts[0]
    decimal_part = parts[1]
    is_neg = integer_part.startswith('-')
    if is_neg:
        integer_part = integer_part[1:]
    if len(integer_part) <= 3:
        formatted = integer_part
    else:
        last3 = integer_part[-3:]
        rest = integer_part[:-3]
        groups = []
        while len(rest) > 2:
            groups.insert(0, rest[-2:])
            rest = rest[:-2]
        if rest:
            groups.insert(0, rest)
        formatted = ','.join(groups) + ',' + last3
    if is_neg:
        formatted = '-' + formatted
    return f"{formatted}.{decimal_part}"


def num_to_words_indian(n):
    ones = ['', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine',
            'Ten', 'Eleven', 'Twelve', 'Thirteen', 'Fourteen', 'Fifteen', 'Sixteen',
            'Seventeen', 'Eighteen', 'Nineteen']
    tens = ['', '', 'Twenty', 'Thirty', 'Forty', 'Fifty', 'Sixty', 'Seventy', 'Eighty', 'Ninety']

    def two_digits(num):
        if num < 20:
            return ones[num]
        return tens[num // 10] + ('' if num % 10 == 0 else ' ' + ones[num % 10])

    def three_digits(num):
        h = num // 100
        rem = num % 100
        res = ''
        if h > 0:
            res += ones[h] + ' Hundred'
            if rem > 0:
                res += ' '
        if rem > 0:
            res += two_digits(rem)
        return res

    if n == 0:
        return 'Zero'

    parts = []
    crores = n // 10000000
    n %= 10000000
    lakhs = n // 100000
    n %= 100000
    thousands = n // 1000
    n %= 1000
    hundreds = n

    if crores > 0:
        parts.append(two_digits(crores) + ' Crore')
    if lakhs > 0:
        parts.append(two_digits(lakhs) + ' Lakh')
    if thousands > 0:
        parts.append(two_digits(thousands) + ' Thousand')
    if hundreds > 0:
        parts.append(three_digits(hundreds))

    return ' '.join(parts)


def amount_to_words_inr(val):
    if val is None:
        return "Indian Rupee Zero Only"
    val = round(float(val), 2)
    rupees = int(val)
    paise = int(round((val - rupees) * 100))
    res = 'Indian Rupee ' + num_to_words_indian(rupees)
    if paise > 0:
        res += ' and ' + num_to_words_indian(paise) + ' Paise'
    return res + ' Only'


def format_invoice_number(invoice):
    """
    Format invoice number matching the official Soteria pattern:
    SSLA/91/N/{FY}/{serial:03d}
    Example: SSLA/91/N/27/028
    """
    if not invoice:
        return "SSLA/91/N/27/001"

    if invoice.invoice_number and invoice.invoice_number.startswith("SSLA/"):
        return invoice.invoice_number

    inv_date = invoice.invoice_date or timezone.localdate()
    # Indian Financial Year suffix: April 2026 - March 2027 -> 27
    fy_suffix = (inv_date.year % 100 + 1) if inv_date.month >= 4 else (inv_date.year % 100)

    serial = invoice.id or 1
    if invoice.invoice_number and invoice.invoice_number.startswith("SINV-"):
        try:
            serial = int(invoice.invoice_number.split("-")[-1])
        except (ValueError, IndexError):
            pass

    return f"SSLA/91/N/{fy_suffix:02d}/{serial:03d}"


def generate_invoice_reference_number(claim, invoice=None):
    """
    Format reference number matching the official Soteria pattern:
    SSLA/91/N/[SurveyType]/[YY+Serial]_[LOCATION]
    Example: SSLA/91/N/M/263100_(DELHI NCR)
    """
    if not claim:
        return "-"

    prefix = "SSLA"
    branch = "91"
    dept = "N"

    # Survey Type mapping (M=Marine, E=Engineering, F=Fire, P=Property, etc.)
    survey_char = "M"
    if claim.survey_type:
        code = (claim.survey_type.code or "").upper()
        if 'MAR' in code:
            survey_char = "M"
        elif 'ENG' in code:
            survey_char = "E"
        elif 'FIRE' in code:
            survey_char = "F"
        elif 'PROP' in code:
            survey_char = "P"
        elif code:
            survey_char = code[0]

    # Year & Serial: e.g. 263100
    date_ref = claim.instruction_date or (invoice.invoice_date if invoice else None) or timezone.localdate()
    yy = date_ref.strftime('%y')
    claim_id = claim.id if claim.id else 1
    serial_str = f"{yy}{3099 + claim_id:04d}"

    # Location / Hub tag: e.g. _(DELHI NCR)
    location_tag = "_(DELHI NCR)"
    if claim.loss_location:
        loc_upper = claim.loss_location.upper()
        if 'MUMBAI' in loc_upper or 'MAHARASHTRA' in loc_upper:
            location_tag = "_(MUMBAI)"
        elif 'KOLKATA' in loc_upper or 'BENGAL' in loc_upper:
            location_tag = "_(KOLKATA)"
        elif 'CHENNAI' in loc_upper or 'TAMIL' in loc_upper:
            location_tag = "_(CHENNAI)"
        elif any(k in loc_upper for k in ['DELHI', 'GURGAON', 'GURUGRAM', 'NOIDA', 'HARYANA']):
            location_tag = "_(DELHI NCR)"

    return f"{prefix}/{branch}/{dept}/{survey_char}/{serial_str}{location_tag}"


def generate_invoice_pdf(invoice):
    """
    Render fee invoice template with WeasyPrint and return raw PDF bytes.
    Matches the official Soteria Tax Invoice standard format.
    """
    import weasyprint
    from reports.services import get_soteria_assets

    assets = get_soteria_assets()
    claim = invoice.claim
    insurer = claim.insurer if claim else None
    insured = claim.insured if claim else None
    policy = claim.policy if claim else None

    # Firm corporate metadata matching official letterhead
    firm_name = getattr(settings, 'FIRM_NAME', 'SOTERIA INSURANCE SURVEYORS AND LOSS ASSESSORS PRIVATE LIMITED')
    firm_address_line1 = getattr(settings, 'FIRM_ADDRESS_LINE1', 'UNIT NO 822B TOWER B4 SPAZE ITECH PARK, SOHNA ROAD SECTOR 49')
    firm_address_line2 = getattr(settings, 'FIRM_ADDRESS_LINE2', 'GURGAON, Haryana, 122018 India')
    
    # Firm GSTIN: prioritize explicit billing GSTIN or Haryana HQ GSTIN
    configured_gstin = getattr(settings, 'FIRM_GSTIN', '')
    if configured_gstin and not configured_gstin.startswith('27AAACS'):
        firm_gstin = configured_gstin
    else:
        firm_gstin = '06ABMCS8969E1ZO'

    firm_license = getattr(settings, 'FIRM_LICENSE', 'IRDA/CORP/SLA-200146')
    firm_cin = getattr(settings, 'FIRM_CIN', 'U66290HR2024PTC119443')
    firm_phone = getattr(settings, 'FIRM_PHONE', '7738922245')
    firm_email = getattr(settings, 'FIRM_EMAIL', 'accounts.india@ssla.global')
    firm_website = getattr(settings, 'FIRM_WEBSITE', 'www.ssla.global')

    # Place of supply calculation (e.g. Delhi (07))
    place_of_supply = '-'
    if insurer and insurer.state:
        state_str = insurer.state.strip()
        code_str = ''
        if insurer.gstin and len(insurer.gstin) >= 2 and insurer.gstin[:2].isdigit():
            code_str = f" ({insurer.gstin[:2]})"
        place_of_supply = f"{state_str.title()}{code_str}"
    elif claim and claim.loss_location:
        place_of_supply = claim.loss_location.split(',')[-1].strip().title()

    # Formatted official Invoice number and Reference number
    formatted_inv_num = format_invoice_number(invoice)
    ref_number = generate_invoice_reference_number(claim, invoice)

    policy_no = policy.policy_number if policy and policy.policy_number else '-'
    claim_no = claim.claim_number if claim and claim.claim_number else '-'

    # Tax label: e.g. "IGST18 (18%)" or "IGST (18%)"
    tax_pct = invoice.tax_percentage or Decimal('18.00')
    tax_pct_int = int(tax_pct) if (tax_pct % 1 == 0) else tax_pct
    tax_label = f"IGST{tax_pct_int} ({tax_pct_int}%)"

    # Line items decoration
    tax_rate = Decimal(str(tax_pct))
    decorated_items = []
    for item in invoice.items.all().order_by('id'):
        qty = Decimal(str(item.quantity or 0))
        rate = Decimal(str(item.rate or 0))
        amount = Decimal(str(item.amount or (qty * rate)))
        tax_amt = round_curr(amount * (tax_rate / Decimal('100.00')))

        decorated_items.append({
            'item': item,
            'description': item.description,
            'hsn_sac': getattr(item, 'hsn_sac', '997162'),
            'quantity': item.quantity,
            'formatted_qty': f"{qty:.2f}",
            'rate': item.rate,
            'formatted_rate': format_inr(rate),
            'tax_percentage': f"{tax_pct_int}%",
            'tax_amount': tax_amt,
            'formatted_tax_amt': format_inr(tax_amt),
            'amount': amount,
            'formatted_amount': format_inr(amount),
        })

    # Bank details & Notes
    default_bank_details = (
        "ACCOUNT HOLDER: SOTERIA INSURANCE SURVEYORS AND LOSS ASSESSORS PRIVATE LIMITED "
        "BANK NAME: INDUSIND BANK BRANCH: AFRICA AVENUE, SAFDARJUNG, NEW DELHI "
        "ACCOUNT NO : 256001800064 IFSC Code: INDB0001555"
    )
    notes_text = invoice.notes.strip() if invoice.notes else "Thanks for your business."

    context = {
        'invoice': invoice,
        'claim': claim,
        'insurer': insurer,
        'insured': insured,
        'policy': policy,
        'items': decorated_items,
        'firm_name': firm_name,
        'firm_address_line1': firm_address_line1,
        'firm_address_line2': firm_address_line2,
        'firm_gstin': firm_gstin,
        'firm_license': firm_license,
        'firm_cin': firm_cin,
        'firm_phone': firm_phone,
        'firm_email': firm_email,
        'firm_website': firm_website,
        'place_of_supply': place_of_supply,
        'formatted_invoice_number': formatted_inv_num,
        'ref_number': ref_number,
        'policy_no': policy_no,
        'claim_no': claim_no,
        'tax_label': tax_label,
        'tax_percentage_display': f"{tax_pct_int}%",
        'formatted_subtotal': format_inr(invoice.subtotal),
        'formatted_tax_amount': format_inr(invoice.tax_amount),
        'formatted_total_amount': format_inr(invoice.total_amount),
        'total_in_words': amount_to_words_inr(invoice.total_amount),
        'notes_text': notes_text,
        'bank_details': default_bank_details,
        'soteria_logo': assets.get('logo', ''),
    }
    html_string = render_to_string('billing/service_invoice_pdf.html', context)
    pdf_bytes = weasyprint.HTML(string=html_string).write_pdf()
    return pdf_bytes
