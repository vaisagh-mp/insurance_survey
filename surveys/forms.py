from django import forms
from django.core.exceptions import ValidationError
from .models import Inspection
from documents.validators import validate_image_file, validate_document_file


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if isinstance(data, (list, tuple)):
            result = [single_file_clean(d, initial) for d in data]
        else:
            result = single_file_clean(data, initial)
        return result


class InspectionForm(forms.ModelForm):
    """
    Inspection Form for Surveyors on Claim's Inspection Tab:
    Includes on-site visit details, extended observations, plus multi-file photo and document uploads.
    """
    extent_of_damage = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Extent of physical loss or damage observed on-site'})
    )
    cause_observations = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Observations regarding origin, ignition source or breakdown cause'})
    )
    salvage_observations = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Salvage mitigation steps, condition, and storage notes'})
    )

    photos = MultipleFileField(
        required=False,
        widget=MultipleFileInput(attrs={'class': 'form-control', 'accept': '.jpg,.jpeg,.png'}),
        help_text="Upload one or more inspection photos (JPG, PNG, max 10MB each)."
    )
    documents = MultipleFileField(
        required=False,
        widget=MultipleFileInput(attrs={'class': 'form-control', 'accept': '.pdf,.jpg,.jpeg,.png'}),
        help_text="Upload relevant inspection documents (PDF, JPG, PNG, max 10MB each)."
    )

    class Meta:
        model = Inspection
        fields = [
            'inspection_date',
            'start_time',
            'end_time',
            'location',
            'person_contacted',
            'contact_number',
            'contact_email',
            'site_representative',
            'reason_for_delay',
            'observations',
            'extent_of_damage',
            'cause_observations',
            'salvage_observations',
            'status',
        ]
        widgets = {
            'inspection_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'start_time': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'end_time': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'location': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Inspection Location / Site Address'}),
            'person_contacted': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Name of person met on site'}),
            'contact_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Contact Phone Number'}),
            'contact_email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Contact Email Address'}),
            'site_representative': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Insured / Insurer representative present'}),
            'reason_for_delay': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'If inspection was delayed after instruction date, state reasons'}),
            'observations': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Detailed general survey observations and inspection notes'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
        }

    def clean_photos(self):
        files = self.files.getlist('photos')
        for f in files:
            validate_image_file(f)
        return files

    def clean_documents(self):
        files = self.files.getlist('documents')
        for f in files:
            validate_document_file(f)
        return files
