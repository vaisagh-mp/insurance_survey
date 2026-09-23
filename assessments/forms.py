from django import forms
from .models import Assessment, AssessmentItem


class AssessmentFinancialForm(forms.ModelForm):
    """Financial parameters adjustment form for the surveyor."""
    class Meta:
        model = Assessment
        fields = [
            'salvage_amount',
            'underinsurance_percentage',
            'depreciation_amount',
            'policy_excess',
            'other_deductions',
            'assessment_remarks',
        ]
        widgets = {
            'salvage_amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'underinsurance_percentage': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'depreciation_amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'policy_excess': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'other_deductions': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'assessment_remarks': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Assessment methodology and loss adjustment remarks'}),
        }


class AssessmentItemForm(forms.ModelForm):
    """Form to add an assessment line item."""
    class Meta:
        model = AssessmentItem
        fields = [
            'item_code',
            'description',
            'category',
            'specification',
            'quantity',
            'rate',
            'claimed_amount',
            'remarks',
        ]
        widgets = {
            'item_code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Item Code (Optional)'}),
            'description': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Item description / affected asset'}),
            'category': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Spares / Labour / Material'}),
            'specification': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Specification / Model'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'id': 'id_item_quantity'}),
            'rate': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'id': 'id_item_rate'}),
            'claimed_amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'remarks': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Line-item remarks / basis of recommendation'}),
        }
