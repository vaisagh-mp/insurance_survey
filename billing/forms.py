from django import forms
from .models import ServiceInvoice, ServiceInvoiceItem


class ServiceInvoiceForm(forms.ModelForm):
    class Meta:
        model = ServiceInvoice
        fields = ['invoice_date', 'due_date', 'tax_percentage', 'notes', 'remarks']
        widgets = {
            'invoice_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'due_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'tax_percentage': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Bank Details / Payment instructions (printed on PDF)'
            }),
            'remarks': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Internal notes (never printed on PDF)'
            }),
        }


class ServiceInvoiceItemForm(forms.ModelForm):
    class Meta:
        model = ServiceInvoiceItem
        fields = ['description', 'quantity', 'rate']
        widgets = {
            'description': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Item description (e.g. Survey Fee, Inspection Fee, Travelling)'
            }),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0.01'}),
            'rate': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0.00'}),
        }
