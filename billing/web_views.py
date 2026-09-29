import json
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.contrib import messages
from django.core.paginator import Paginator
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db.models import Q

from config.concurrency import check_optimistic_concurrency
from django.utils import timezone
from django.db.models import Q

from claims.models import Claim, Insurer
from claims.web_views import admin_required
from .models import ServiceInvoice, ServiceInvoiceItem
from .forms import ServiceInvoiceForm, ServiceInvoiceItemForm
from .services import (
    recalculate_invoice,
    mark_invoice_sent,
    record_invoice_payment,
    cancel_invoice,
    generate_invoice_pdf,
    add_invoice_item,
    update_invoice_item,
    delete_invoice_item,
)


@admin_required
def invoice_list(request):
    """
    Top-level admin view listing all ServiceInvoices across claims.
    Filterable by status, insurer, and search keyword.
    """
    invoices = ServiceInvoice.objects.select_related(
        'claim', 'claim__insurer', 'claim__insured', 'created_by'
    ).order_by('-invoice_date', '-created_at')

    status_filter = request.GET.get('status', '').strip().upper()
    if status_filter:
        invoices = invoices.filter(status=status_filter)

    insurer_id = request.GET.get('insurer', '').strip()
    if insurer_id:
        invoices = invoices.filter(claim__insurer_id=insurer_id)

    q = request.GET.get('q', '').strip()
    if q:
        invoices = invoices.filter(
            Q(invoice_number__icontains=q) |
            Q(claim__claim_number__icontains=q) |
            Q(claim__insurer__company_name__icontains=q) |
            Q(claim__insured__name__icontains=q) |
            Q(payment_reference__icontains=q)
        )

    paginator = Paginator(invoices, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    insurers = Insurer.objects.filter(is_active=True).order_by('company_name')

    context = {
        'page_obj': page_obj,
        'insurers': insurers,
        'current_status': status_filter,
        'current_insurer': insurer_id,
        'search_query': q,
        'total_count': paginator.count,
        'status_choices': ServiceInvoice.Status.choices,
    }
    return render(request, 'billing/invoice_list.html', context)


@admin_required
def claim_billing_create(request, pk):
    """
    Create a new fee ServiceInvoice for a claim.
    Rejects if a non-cancelled invoice already exists for this claim.
    """
    claim = get_object_or_404(Claim, pk=pk)
    is_json = request.content_type == 'application/json' or 'application/json' in request.headers.get('Accept', '')

    if request.method != 'POST':
        if is_json:
            return JsonResponse({'detail': 'Method not allowed'}, status=405)
        return redirect(f"/claims/{claim.pk}/?tab=billing")

    if request.content_type == 'application/json':
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({'detail': 'Invalid JSON body'}, status=400)
    else:
        data = request.POST

    conflict = check_optimistic_concurrency(claim, base_updated_at=data.get('base_updated_at'), if_match=request.headers.get('If-Match'))
    if conflict:
        return JsonResponse(conflict, status=409)

    # Check for existing non-cancelled invoice
    existing = ServiceInvoice.objects.filter(claim=claim).exclude(
        status=ServiceInvoice.Status.CANCELLED
    ).first()
    if existing:
        msg = f"A non-cancelled service invoice ({existing.invoice_number}) already exists for this claim."
        if is_json:
            return JsonResponse({'detail': msg, 'code': 'conflict'}, status=409)
        messages.error(request, msg)
        return redirect(f"/claims/{claim.pk}/?tab=billing")

    invoice_date_str = data.get('invoice_date')
    due_date_str = data.get('due_date')
    tax_pct_str = data.get('tax_percentage', '18.00')
    notes = (data.get('notes') or '').strip()
    remarks = (data.get('remarks') or '').strip()

    invoice_date = timezone.datetime.strptime(invoice_date_str, '%Y-%m-%d').date() if invoice_date_str else timezone.localdate()
    due_date = timezone.datetime.strptime(due_date_str, '%Y-%m-%d').date() if due_date_str else (invoice_date + timezone.timedelta(days=30))
    tax_pct = Decimal(tax_pct_str) if tax_pct_str else Decimal('18.00')

    invoice = ServiceInvoice(
        claim=claim,
        invoice_date=invoice_date,
        due_date=due_date,
        tax_percentage=tax_pct,
        notes=notes,
        remarks=remarks,
        created_by=request.user,
        status=ServiceInvoice.Status.DRAFT,
    )
    try:
        invoice.full_clean()
        invoice.save()
        if is_json:
            return JsonResponse({
                'status': 'success',
                'id': invoice.id,
                'invoice_number': invoice.invoice_number,
                'message': f"Fee invoice {invoice.invoice_number} created successfully as Draft."
            }, status=201)
        messages.success(request, f"Fee invoice {invoice.invoice_number} created successfully as Draft.")
    except ValidationError as e:
        if is_json:
            errors = getattr(e, 'message_dict', {'non_field_errors': [str(e)]})
            return JsonResponse({'detail': f"Failed to create invoice: {e}", 'errors': errors}, status=400)
        messages.error(request, f"Failed to create invoice: {e}")

    return redirect(f"/claims/{claim.pk}/?tab=billing")


@admin_required
def claim_billing_save(request, pk):
    """
    Update header fields of a DRAFT ServiceInvoice.
    Locked: Rejects if status is not DRAFT.
    """
    claim = get_object_or_404(Claim, pk=pk)
    invoice = get_object_or_404(
        ServiceInvoice.objects.filter(claim=claim).exclude(status=ServiceInvoice.Status.CANCELLED)
    )
    is_json = request.content_type == 'application/json' or 'application/json' in request.headers.get('Accept', '')

    if request.method != 'POST':
        if is_json:
            return JsonResponse({'detail': 'Method not allowed'}, status=405)
        return redirect(f"/claims/{claim.pk}/?tab=billing")

    if invoice.status != ServiceInvoice.Status.DRAFT:
        msg = f"Cannot modify invoice #{invoice.invoice_number}. Only DRAFT invoices can be edited."
        if is_json:
            return JsonResponse({'detail': msg, 'code': 'locked'}, status=400)
        messages.error(request, msg)
        return HttpResponse(msg, status=400)

    if request.content_type == 'application/json':
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({'detail': 'Invalid JSON body'}, status=400)
    else:
        data = request.POST

    conflict = check_optimistic_concurrency(invoice, base_updated_at=data.get('base_updated_at'), if_match=request.headers.get('If-Match'))
    if conflict:
        return JsonResponse(conflict, status=409)

    invoice_date_str = data.get('invoice_date')
    due_date_str = data.get('due_date')
    tax_pct_str = data.get('tax_percentage')
    notes = data.get('notes')
    remarks = data.get('remarks')

    if invoice_date_str:
        invoice.invoice_date = timezone.datetime.strptime(invoice_date_str, '%Y-%m-%d').date()
    if due_date_str:
        invoice.due_date = timezone.datetime.strptime(due_date_str, '%Y-%m-%d').date()
    if tax_pct_str:
        invoice.tax_percentage = Decimal(tax_pct_str)
    if notes is not None:
        invoice.notes = notes.strip()
    if remarks is not None:
        invoice.remarks = remarks.strip()

    invoice.save()
    recalculate_invoice(invoice)

    if is_json:
        return JsonResponse({
            'status': 'success',
            'id': invoice.id,
            'invoice_number': invoice.invoice_number,
            'total_amount': str(invoice.total_amount),
            'message': f"Invoice {invoice.invoice_number} updated and recalculated."
        }, status=200)

    messages.success(request, f"Invoice {invoice.invoice_number} updated and recalculated.")
    return redirect(f"/claims/{claim.pk}/?tab=billing")


@admin_required
def claim_billing_item_add(request, pk):
    """
    Add a line item to a DRAFT ServiceInvoice and immediately recalculate.
    Locked: Rejects if status is not DRAFT.
    """
    claim = get_object_or_404(Claim, pk=pk)
    invoice = get_object_or_404(
        ServiceInvoice.objects.filter(claim=claim).exclude(status=ServiceInvoice.Status.CANCELLED)
    )
    is_json = request.content_type == 'application/json' or 'application/json' in request.headers.get('Accept', '')

    if request.method != 'POST':
        if is_json:
            return JsonResponse({'detail': 'Method not allowed'}, status=405)
        return redirect(f"/claims/{claim.pk}/?tab=billing")

    if invoice.status != ServiceInvoice.Status.DRAFT:
        msg = f"Cannot add line item. Invoice #{invoice.invoice_number} is in '{invoice.status}' status and is locked."
        if is_json:
            return JsonResponse({'detail': msg, 'code': 'locked'}, status=400)
        messages.error(request, msg)
        return HttpResponse(msg, status=400)

    if request.content_type == 'application/json':
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({'detail': 'Invalid JSON body'}, status=400)
    else:
        data = request.POST

    conflict = check_optimistic_concurrency(invoice, base_updated_at=data.get('base_updated_at'), if_match=request.headers.get('If-Match'))
    if conflict:
        return JsonResponse(conflict, status=409)

    description = (data.get('description') or '').strip()
    qty_str = data.get('quantity', '1')
    rate_str = data.get('rate', '0')

    if not description:
        if is_json:
            return JsonResponse({'detail': 'Description is required for an invoice line item.', 'errors': {'description': 'This field is required.'}}, status=400)
        messages.error(request, "Description is required for an invoice line item.")
        return redirect(f"/claims/{claim.pk}/?tab=billing")

    try:
        qty = Decimal(qty_str) if qty_str else Decimal('1.00')
        rate = Decimal(rate_str) if rate_str else Decimal('0.00')
        item = add_invoice_item(invoice, description, qty, rate)
        if is_json:
            return JsonResponse({
                'status': 'success',
                'id': item.id,
                'description': item.description,
                'total': str(item.amount),
                'message': f"Added item '{description}' and updated invoice totals."
            }, status=201)
        messages.success(request, f"Added item '{description}' and updated invoice totals.")
    except (ValidationError, Exception) as e:
        if is_json:
            return JsonResponse({'detail': f"Error adding item: {e}", 'errors': {'non_field_errors': [str(e)]}}, status=400)
        messages.error(request, f"Error adding item: {e}")

    return redirect(f"/claims/{claim.pk}/?tab=billing")


@admin_required
def claim_billing_item_edit(request, pk, item_id):
    """
    Edit a line item on a DRAFT ServiceInvoice and immediately recalculate.
    Locked: Rejects if status is not DRAFT.
    """
    claim = get_object_or_404(Claim, pk=pk)
    item = get_object_or_404(ServiceInvoiceItem, pk=item_id, invoice__claim=claim)
    invoice = item.invoice
    is_json = request.content_type == 'application/json' or 'application/json' in request.headers.get('Accept', '')

    if request.method != 'POST':
        if is_json:
            return JsonResponse({'detail': 'Method not allowed'}, status=405)
        return redirect(f"/claims/{claim.pk}/?tab=billing")

    if invoice.status != ServiceInvoice.Status.DRAFT:
        msg = f"Cannot edit line item. Invoice #{invoice.invoice_number} is in '{invoice.status}' status and is locked."
        if is_json:
            return JsonResponse({'detail': msg, 'code': 'locked'}, status=400)
        messages.error(request, msg)
        return HttpResponse(msg, status=400)

    if request.content_type == 'application/json':
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({'detail': 'Invalid JSON body'}, status=400)
    else:
        data = request.POST

    conflict = check_optimistic_concurrency(item, base_updated_at=data.get('base_updated_at'), if_match=request.headers.get('If-Match'))
    if conflict:
        return JsonResponse(conflict, status=409)

    description = (data.get('description') or '').strip()
    qty_str = data.get('quantity')
    rate_str = data.get('rate')

    try:
        update_invoice_item(
            item,
            description=description if description else None,
            quantity=Decimal(qty_str) if qty_str else None,
            rate=Decimal(rate_str) if rate_str else None
        )
        if is_json:
            return JsonResponse({
                'status': 'success',
                'id': item.id,
                'description': item.description,
                'total': str(item.amount),
                'message': f"Item '{item.description}' updated and invoice recalculated."
            }, status=200)
        messages.success(request, f"Item '{item.description}' updated and invoice recalculated.")
    except (ValidationError, Exception) as e:
        if is_json:
            return JsonResponse({'detail': f"Error updating item: {e}", 'errors': {'non_field_errors': [str(e)]}}, status=400)
        messages.error(request, f"Error updating item: {e}")

    return redirect(f"/claims/{claim.pk}/?tab=billing")


@admin_required
def claim_billing_item_delete(request, pk, item_id):
    """
    Delete a line item from a DRAFT ServiceInvoice and immediately recalculate.
    Locked: Rejects if status is not DRAFT.
    """
    claim = get_object_or_404(Claim, pk=pk)
    item = get_object_or_404(ServiceInvoiceItem, pk=item_id, invoice__claim=claim)
    invoice = item.invoice

    if request.method == 'POST':
        if invoice.status != ServiceInvoice.Status.DRAFT:
            msg = f"Cannot delete line item. Invoice #{invoice.invoice_number} is in '{invoice.status}' status and is locked."
            messages.error(request, msg)
            return HttpResponse(msg, status=400)

        desc = item.description
        delete_invoice_item(item)
        messages.success(request, f"Deleted item '{desc}' and updated invoice totals.")

    return redirect(f"/claims/{claim.pk}/?tab=billing")


@admin_required
def claim_billing_mark_sent(request, pk):
    """
    Mark invoice as SENT (transitions from DRAFT only).
    """
    claim = get_object_or_404(Claim, pk=pk)
    invoice = get_object_or_404(
        ServiceInvoice.objects.filter(claim=claim).exclude(status=ServiceInvoice.Status.CANCELLED)
    )
    is_json = request.content_type == 'application/json' or 'application/json' in request.headers.get('Accept', '')

    if request.method != 'POST':
        if is_json:
            return JsonResponse({'detail': 'Method not allowed'}, status=405)
        return redirect(f"/claims/{claim.pk}/?tab=billing")

    if request.content_type == 'application/json':
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({'detail': 'Invalid JSON body'}, status=400)
    else:
        data = request.POST

    conflict = check_optimistic_concurrency(invoice, base_updated_at=data.get('base_updated_at'), if_match=request.headers.get('If-Match'))
    if conflict:
        return JsonResponse(conflict, status=409)

    try:
        mark_invoice_sent(invoice, request.user)
        if is_json:
            return JsonResponse({
                'status': 'success',
                'id': invoice.id,
                'status_code': invoice.status,
                'message': f"Invoice {invoice.invoice_number} marked as SENT."
            }, status=200)
        messages.success(request, f"Invoice {invoice.invoice_number} marked as SENT.")
    except ValidationError as e:
        err_msg = str(e.message if hasattr(e, 'message') else e)
        if is_json:
            return JsonResponse({'detail': err_msg, 'code': 'invalid_transition'}, status=400)
        messages.error(request, err_msg)

    return redirect(f"/claims/{claim.pk}/?tab=billing")


@admin_required
def claim_billing_record_payment(request, pk):
    """
    Record payment for invoice (transitions from SENT only).
    """
    claim = get_object_or_404(Claim, pk=pk)
    invoice = get_object_or_404(
        ServiceInvoice.objects.filter(claim=claim).exclude(status=ServiceInvoice.Status.CANCELLED)
    )
    is_json = request.content_type == 'application/json' or 'application/json' in request.headers.get('Accept', '')

    if request.method != 'POST':
        if is_json:
            return JsonResponse({'detail': 'Method not allowed'}, status=405)
        return redirect(f"/claims/{claim.pk}/?tab=billing")

    if request.content_type == 'application/json':
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({'detail': 'Invalid JSON body'}, status=400)
    else:
        data = request.POST

    conflict = check_optimistic_concurrency(invoice, base_updated_at=data.get('base_updated_at'), if_match=request.headers.get('If-Match'))
    if conflict:
        return JsonResponse(conflict, status=409)

    ref = (data.get('payment_reference') or '').strip()
    try:
        record_invoice_payment(invoice, request.user, payment_reference=ref)
        if is_json:
            return JsonResponse({
                'status': 'success',
                'id': invoice.id,
                'status_code': invoice.status,
                'payment_reference': invoice.payment_reference,
                'message': f"Payment recorded for invoice {invoice.invoice_number}."
            }, status=200)
        messages.success(request, f"Payment recorded for invoice {invoice.invoice_number}.")
    except ValidationError as e:
        err_msg = str(e.message if hasattr(e, 'message') else e)
        if is_json:
            return JsonResponse({'detail': err_msg, 'code': 'invalid_transition'}, status=400)
        messages.error(request, err_msg)

    return redirect(f"/claims/{claim.pk}/?tab=billing")


@admin_required
def claim_billing_cancel(request, pk):
    """
    Cancel an invoice with a mandatory non-blank reason.
    Appends reason into invoice remarks.
    """
    claim = get_object_or_404(Claim, pk=pk)
    invoice = get_object_or_404(
        ServiceInvoice.objects.filter(claim=claim).exclude(status=ServiceInvoice.Status.CANCELLED)
    )
    is_json = request.content_type == 'application/json' or 'application/json' in request.headers.get('Accept', '')

    if request.method != 'POST':
        if is_json:
            return JsonResponse({'detail': 'Method not allowed'}, status=405)
        return redirect(f"/claims/{claim.pk}/?tab=billing")

    if request.content_type == 'application/json':
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({'detail': 'Invalid JSON body'}, status=400)
    else:
        data = request.POST

    conflict = check_optimistic_concurrency(invoice, base_updated_at=data.get('base_updated_at'), if_match=request.headers.get('If-Match'))
    if conflict:
        return JsonResponse(conflict, status=409)

    reason = (data.get('reason') or '').strip()
    if not reason:
        if is_json:
            return JsonResponse({'detail': 'Cancellation reason is required.', 'errors': {'reason': 'This field is required.'}}, status=400)
        messages.error(request, "Cancellation reason is required.")
        return redirect(f"/claims/{claim.pk}/?tab=billing")

    try:
        cancel_invoice(invoice, request.user, reason=reason)
        if is_json:
            return JsonResponse({
                'status': 'success',
                'id': invoice.id,
                'status_code': invoice.status,
                'message': f"Invoice {invoice.invoice_number} cancelled."
            }, status=200)
        messages.success(request, f"Invoice {invoice.invoice_number} cancelled.")
    except ValidationError as e:
        err_msg = str(e.message if hasattr(e, 'message') else e)
        if is_json:
            return JsonResponse({'detail': err_msg, 'code': 'invalid_transition'}, status=400)
        messages.error(request, err_msg)

    return redirect(f"/claims/{claim.pk}/?tab=billing")



@admin_required
def claim_billing_pdf(request, pk):
    """
    Generate and stream WeasyPrint PDF for the ServiceInvoice.
    """
    claim = get_object_or_404(Claim, pk=pk)
    # Can view PDF of active invoice or specific invoice pk if provided
    inv_id = request.GET.get('invoice_id')
    if inv_id:
        invoice = get_object_or_404(ServiceInvoice, pk=inv_id, claim=claim)
    else:
        invoice = get_object_or_404(
            ServiceInvoice.objects.filter(claim=claim).exclude(status=ServiceInvoice.Status.CANCELLED)
        )

    pdf_bytes = generate_invoice_pdf(invoice)
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    filename = f"{invoice.invoice_number}.pdf"
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    return response
