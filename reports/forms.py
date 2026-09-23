from django import forms
from .models import ILA, ISR, FSR


class ILAForm(forms.ModelForm):
    class Meta:
        model = ILA
        fields = [
            'report_number',
            'report_date',
            'instruction_date',
            'instruction_source',
            'visit_date',
            'visit_start_time',
            'visit_end_time',
            'inspection_location',
            'person_contacted',
            'contact_number',
            'contact_email',
            'reason_for_delay',
            'policy_number',
            'policy_type',
            'policy_period',
            'commodity',
            'sum_insured',
            'policy_excess',
            'survey_and_inspection',
            'extent_of_damage',
            'cause_of_damage',
            'salvage_prospect',
            'estimated_loss',
            'claimed_amount',
            'policy_liability',
            'budgetary_reserve',
            'remarks',
        ]
        widgets = {
            'report_number': forms.TextInput(attrs={'class': 'form-control'}),
            'report_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'instruction_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'instruction_source': forms.TextInput(attrs={'class': 'form-control'}),
            'visit_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'visit_start_time': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'visit_end_time': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'inspection_location': forms.TextInput(attrs={'class': 'form-control'}),
            'person_contacted': forms.TextInput(attrs={'class': 'form-control'}),
            'contact_number': forms.TextInput(attrs={'class': 'form-control'}),
            'contact_email': forms.EmailInput(attrs={'class': 'form-control'}),
            'reason_for_delay': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'policy_number': forms.TextInput(attrs={'class': 'form-control'}),
            'policy_type': forms.TextInput(attrs={'class': 'form-control'}),
            'policy_period': forms.TextInput(attrs={'class': 'form-control'}),
            'commodity': forms.TextInput(attrs={'class': 'form-control'}),
            'sum_insured': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'policy_excess': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'survey_and_inspection': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'extent_of_damage': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'cause_of_damage': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'salvage_prospect': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'estimated_loss': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'claimed_amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'policy_liability': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'budgetary_reserve': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'remarks': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }


class ISRForm(forms.ModelForm):
    class Meta:
        model = ISR
        fields = [
            'report_number',
            'report_date',
            'introduction',
            'occurrence_details',
            'survey_details',
            'extent_of_damage',
            'cause_of_loss',
            'initial_assessment',
            'policy_liability',
            'documents_received',
            'documents_pending',
            'remarks',
            'recommendation',
        ]
        widgets = {
            'report_number': forms.TextInput(attrs={'class': 'form-control'}),
            'report_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'introduction': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'occurrence_details': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'survey_details': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'extent_of_damage': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'cause_of_loss': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'initial_assessment': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'policy_liability': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'documents_received': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'documents_pending': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'remarks': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'recommendation': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }


class FSRForm(forms.ModelForm):
    class Meta:
        model = FSR
        fields = [
            'report_number',
            'report_date',
            'introduction',
            'occurrence_details',
            'survey_details',
            'extent_of_loss',
            'cause_of_loss',
            'adequacy_of_sum_insured',
            'value_at_risk',
            'sum_insured',
            'underinsurance_percentage',
            'salvage_description',
            'salvage_amount',
            'insured_claim_description',
            'admissibility',
            'policy_coverage',
            'policy_exclusions',
            'breach_of_warranty',
            'warranty_details',
            'remarks',
            'final_opinion',
        ]
        widgets = {
            'report_number': forms.TextInput(attrs={'class': 'form-control'}),
            'report_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'introduction': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'occurrence_details': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'survey_details': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'extent_of_loss': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'cause_of_loss': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'adequacy_of_sum_insured': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Explanation of value-at-risk, basis of underinsurance assessment, balance sheet/P&L details...'}),
            'value_at_risk': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'sum_insured': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'underinsurance_percentage': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'salvage_description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'salvage_amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'insured_claim_description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'admissibility': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'policy_coverage': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'policy_exclusions': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'breach_of_warranty': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'warranty_details': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'remarks': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'final_opinion': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['policy_coverage'].required = False
        self.fields['policy_exclusions'].required = False
        self.fields['adequacy_of_sum_insured'].required = False
