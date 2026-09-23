from django import forms
from .models import Claim, Insurer, Insured, Policy, Priority
from surveys.models import SurveyType, FireClaimDetails, EngineeringClaimDetails, MarineClaimDetails, PropertyClaimDetails


class InsurerForm(forms.ModelForm):
    class Meta:
        model = Insurer
        fields = [
            'company_name',
            'branch_name',
            'contact_person',
            'phone',
            'email',
            'address',
            'city',
            'state',
            'pincode',
            'is_active'
        ]
        widgets = {
            'company_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Company / Insurer Name'}),
            'branch_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Branch / Office Name'}),
            'contact_person': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Contact Person'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Phone Number'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email Address'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Full Address'}),
            'city': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'City'}),
            'state': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'State'}),
            'pincode': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'PIN / Postal Code'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class InsuredForm(forms.ModelForm):
    class Meta:
        model = Insured
        fields = [
            'name',
            'company_name',
            'contact_person',
            'phone',
            'email',
            'gstin',
            'address',
            'city',
            'state',
            'pincode',
            'is_active'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Insured Person / Entity Name'}),
            'company_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Company Name (if corporate)'}),
            'contact_person': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Key Contact Person'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Phone Number'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email Address'}),
            'gstin': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'GSTIN Number (Optional)'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Full Address'}),
            'city': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'City'}),
            'state': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'State'}),
            'pincode': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'PIN / Postal Code'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class PolicyForm(forms.ModelForm):
    class Meta:
        model = Policy
        fields = [
            'insurer',
            'policy_number',
            'policy_type',
            'start_datetime',
            'end_datetime',
            'sum_insured',
            'excess',
            'commodity',
            'subject_matter',
            'remarks'
        ]
        widgets = {
            'insurer': forms.Select(attrs={'class': 'form-control'}),
            'policy_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. POL-FIR-2026-0001'}),
            'policy_type': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Standard Fire & Special Perils'}),
            'start_datetime': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'end_datetime': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'sum_insured': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'excess': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'commodity': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Commodity / Goods Description'}),
            'subject_matter': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Subject Matter Details'}),
            'remarks': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Policy Remarks (Optional)'}),
        }


class ClaimCreateForm(forms.ModelForm):
    """
    Multi-section claim registration form:
    Section A (Claim): claim_number, report_number, survey_type, instruction_date, instruction_source, priority
    Section B (Insurer): insurer
    Section C (Insured): insured
    Section D (Policy): policy
    Section E (Loss): date_of_loss, loss_location, nature_of_loss, claimed_amount, claim_description, contact_person, contact_phone, contact_email
    """
    class Meta:
        model = Claim
        fields = [
            # Section A
            'claim_number',
            'report_number',
            'survey_type',
            'instruction_date',
            'instruction_source',
            'priority',
            # Section B
            'insurer',
            # Section C
            'insured',
            # Section D
            'policy',
            # Section E
            'date_of_loss',
            'nature_of_loss',
            'loss_location',
            'claimed_amount',
            'claim_description',
            'contact_person',
            'contact_phone',
            'contact_email',
        ]
        widgets = {
            'claim_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Leave blank to auto-generate (e.g. CLM-00001)'}),
            'report_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. REP-2026-001 (Optional)'}),
            'survey_type': forms.Select(attrs={'class': 'form-control', 'id': 'id_survey_type'}),
            'instruction_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'instruction_source': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Underwriter / Claims Dept'}),
            'priority': forms.Select(attrs={'class': 'form-control'}),
            'insurer': forms.Select(attrs={'class': 'form-control', 'id': 'id_insurer'}),
            'insured': forms.Select(attrs={'class': 'form-control', 'id': 'id_insured'}),
            'policy': forms.Select(attrs={'class': 'form-control', 'id': 'id_policy'}),
            'date_of_loss': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'nature_of_loss': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Fire in Warehouse / Machine Breakdown'}),
            'loss_location': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Detailed location / site of incident'}),
            'claimed_amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': '0.00'}),
            'claim_description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Initial circumstances and narrative of loss...'}),
            'contact_person': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Site contact person'}),
            'contact_phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Phone number'}),
            'contact_email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email address'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['survey_type'].queryset = SurveyType.objects.filter(is_active=True)
        self.fields['insurer'].queryset = Insurer.objects.filter(is_active=True)
        self.fields['insured'].queryset = Insured.objects.filter(is_active=True)
        self.fields['policy'].queryset = Policy.objects.select_related('insurer').all()

        # Enforce required rules from the spec:
        # survey type, insurer, insured, policy all required
        self.fields['survey_type'].required = True
        self.fields['insurer'].required = True
        self.fields['insured'].required = True
        self.fields['policy'].required = True
        self.fields['instruction_date'].required = True
        self.fields['instruction_source'].required = True
        self.fields['date_of_loss'].required = True
        self.fields['nature_of_loss'].required = True
        self.fields['loss_location'].required = True
        self.fields['priority'].required = False
        self.fields['priority'].initial = Priority.MEDIUM

    def clean_priority(self):
        return self.cleaned_data.get('priority') or Priority.MEDIUM


# --- Survey Detail ModelForms ---

class FireClaimDetailsForm(forms.ModelForm):
    class Meta:
        model = FireClaimDetails
        exclude = ['claim', 'created_at', 'updated_at']
        widgets = {
            'construction_details': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Class 1 RCC Construction'}),
            'occupancy': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Manufacturing / Storage'}),
            'building_description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Description of buildings, sheds, boundary'}),
            'fire_protection_details': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Hydrants, sprinklers, extinguishers available'}),
            'fire_brigade_informed': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'fire_brigade_details': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Fire station name, attendance time, report ref'}),
            'police_informed': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'police_details': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Police station, GD / FIR entry details'}),
            'fire_cause': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Probable or established cause of fire'}),
            'cause_established': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'point_of_origin': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Electric Panel Room / Bay 3'}),
            'storage_details': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Storage arrangement / heights'}),
            'machinery_details': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Machinery installed at affected area'}),
            'stock_details': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Raw materials / finished stocks in vicinity'}),
            'salvage_observation': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Segregation and salvage protection'}),
        }


class EngineeringClaimDetailsForm(forms.ModelForm):
    class Meta:
        model = EngineeringClaimDetails
        exclude = ['claim', 'created_at', 'updated_at']
        widgets = {
            'equipment_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 500 KVA Diesel Generator'}),
            'manufacturer': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Manufacturer / OEM'}),
            'model': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Model / Type'}),
            'serial_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Equipment Serial Number'}),
            'year_of_manufacture': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'YYYY'}),
            'installation_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'machine_location': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Plant bay / Machine location'}),
            'breakdown_description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Circumstances leading to breakdown'}),
            'damage_description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Physical damage observed on components'}),
            'cause_of_breakdown': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Mechanical / electrical breakdown cause'}),
            'repair_estimate': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'replacement_cost': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'parts_cost': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'labour_cost': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'testing_cost': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'salvage': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Damaged parts salvage prospects'}),
        }


class MarineClaimDetailsForm(forms.ModelForm):
    class Meta:
        model = MarineClaimDetails
        exclude = ['claim', 'created_at', 'updated_at']
        widgets = {
            'vessel_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Vessel / Carrier name / Vehicle Reg'}),
            'voyage_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Voyage or Trip number'}),
            'port_of_loading': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Port / Place of loading'}),
            'port_of_discharge': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Port / Place of destination'}),
            'place_of_survey': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Exact place where survey was held'}),
            'cargo_description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Description of cargo, packing, marks & numbers'}),
            'consignor': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Consignor / Shipper'}),
            'consignee': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Consignee / Receiver'}),
            'carrier': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Shipping line / Transporter'}),
            'bill_of_lading_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'B/L or LR / Consignment Note No.'}),
            'container_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Container number & Seal number'}),
            'package_count': forms.NumberInput(attrs={'class': 'form-control'}),
            'damage_description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Details of damage, wetting, shortage or breakage'}),
            'transit_details': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Sea / Road / Air route particulars'}),
            'packing_condition': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Condition of external and internal packing'}),
            'salvage_details': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Salvage potential and preservation measures'}),
        }


class PropertyClaimDetailsForm(forms.ModelForm):
    class Meta:
        model = PropertyClaimDetails
        exclude = ['claim', 'created_at', 'updated_at']
        widgets = {
            'property_type': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Commercial Complex / Residential Flat'}),
            'occupancy': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Retail Showroom / Tenanted Office'}),
            'construction_type': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Pucca / Semi-Pucca / Steel structure'}),
            'building_area': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'Sq. meters / Sq. feet'}),
            'number_of_floors': forms.NumberInput(attrs={'class': 'form-control'}),
            'building_description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Structure, age, maintenance condition'}),
            'contents_description': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Furniture, fixtures, fittings'}),
            'stock_description': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Stock items affected'}),
            'damage_description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Extent of damage to building and contents'}),
            'repair_estimate': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'replacement_cost': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'salvage': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Disposal / salvage prospects'}),
        }
