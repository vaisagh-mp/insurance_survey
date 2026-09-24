from django.contrib import admin
from .models import ServiceInvoice, ServiceInvoiceItem


class ServiceInvoiceItemInline(admin.TabularInline):
    model = ServiceInvoiceItem
    extra = 1
    readonly_fields = ('amount',)


@admin.register(ServiceInvoice)
class ServiceInvoiceAdmin(admin.ModelAdmin):
    list_display = (
        'invoice_number',
        'claim',
        'invoice_date',
        'due_date',
        'status',
        'total_amount',
        'created_by',
    )
    list_filter = ('status', 'invoice_date', 'due_date')
    search_fields = ('invoice_number', 'claim__claim_number', 'payment_reference')
    readonly_fields = ('invoice_number', 'subtotal', 'tax_amount', 'total_amount', 'created_at', 'updated_at')
    inlines = [ServiceInvoiceItemInline]


@admin.register(ServiceInvoiceItem)
class ServiceInvoiceItemAdmin(admin.ModelAdmin):
    list_display = ('invoice', 'description', 'quantity', 'rate', 'amount')
    search_fields = ('description', 'invoice__invoice_number')
    readonly_fields = ('amount', 'created_at', 'updated_at')
