from django import forms
from .models import Requirement, ClaimDocument


class RequirementForm(forms.ModelForm):
    class Meta:
        model = Requirement
        fields = [
            'description',
            'requested_from',
            'requested_date',
            'due_date',
            'status',
            'remarks',
            'related_document',
        ]
        widgets = {
            'description': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Fire brigade attendance report / Purchase invoices'}),
            'requested_from': forms.Select(attrs={'class': 'form-control'}),
            'requested_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'due_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'remarks': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Optional internal notes'}),
            'related_document': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        claim = kwargs.pop('claim', None)
        super().__init__(*args, **kwargs)
        if claim:
            self.fields['related_document'].queryset = ClaimDocument.objects.filter(claim=claim)
        else:
            self.fields['related_document'].queryset = ClaimDocument.objects.none()
        self.fields['related_document'].required = False


class ClaimDocumentForm(forms.ModelForm):
    class Meta:
        model = ClaimDocument
        fields = [
            'document_type',
            'document_number',
            'document_date',
            'description',
            'file',
        ]
        widgets = {
            'document_type': forms.Select(attrs={'class': 'form-control'}),
            'document_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. POL-9921 / INV-2026-44'}),
            'document_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'description': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Brief description or remarks'}),
            'file': forms.FileInput(attrs={'class': 'form-control'}),
        }
