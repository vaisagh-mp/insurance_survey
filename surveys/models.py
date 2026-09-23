from decimal import Decimal
from django.conf import settings
from django.db import models
from documents.validators import validate_image_extension, validate_image_size


class SurveyType(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'nis_survey_type'
        verbose_name = "Survey Type"
        verbose_name_plural = "Survey Types"
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.code})"


class Inspection(models.Model):
    class Status(models.TextChoices):
        SCHEDULED = 'SCHEDULED', 'Scheduled'
        COMPLETED = 'COMPLETED', 'Completed'

    claim = models.ForeignKey(
        'claims.Claim',
        on_delete=models.CASCADE,
        related_name='inspections'
    )
    surveyor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        limit_choices_to={'role': 'SURVEYOR'},
        related_name='inspections'
    )
    inspection_date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    location = models.CharField(max_length=255)
    person_contacted = models.CharField(max_length=150)
    contact_number = models.CharField(max_length=30)
    contact_email = models.EmailField(blank=True)
    reason_for_delay = models.TextField(blank=True)
    site_representative = models.CharField(max_length=150, blank=True)
    observations = models.TextField(blank=True)
    extent_of_damage = models.TextField(blank=True)
    cause_observations = models.TextField(blank=True)
    salvage_observations = models.TextField(blank=True)
    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.SCHEDULED
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'nis_inspection'
        ordering = ['-inspection_date', '-start_time']
        verbose_name = 'Inspection'
        verbose_name_plural = 'Inspections'

    def __str__(self):
        return f"Inspection for {self.claim.claim_number} on {self.inspection_date} ({self.get_status_display()})"


class InspectionPhoto(models.Model):
    class Category(models.TextChoices):
        SITE = 'SITE', 'Site'
        DAMAGE = 'DAMAGE', 'Damage'
        MACHINERY = 'MACHINERY', 'Machinery'
        STOCK = 'STOCK', 'Stock'
        DOCUMENT = 'DOCUMENT', 'Document'
        SALVAGE = 'SALVAGE', 'Salvage'
        OTHER = 'OTHER', 'Other'

    inspection = models.ForeignKey(
        Inspection,
        on_delete=models.CASCADE,
        related_name='photos'
    )
    image = models.ImageField(
        upload_to="inspection_photos/%Y/%m/",
        validators=[validate_image_extension, validate_image_size]
    )
    caption = models.CharField(max_length=255, blank=True)
    category = models.CharField(
        max_length=30,
        choices=Category.choices,
        default=Category.SITE
    )
    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True
    )
    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True
    )
    captured_at = models.DateTimeField(null=True, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='uploaded_photos'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'nis_inspection_photo'
        ordering = ['-created_at']
        verbose_name = 'Inspection Photo'
        verbose_name_plural = 'Inspection Photos'

    def __str__(self):
        desc = self.caption or f"Photo #{self.pk}"
        return f"{self.get_category_display()} - {desc} ({self.inspection.claim.claim_number})"


class InspectionObservation(models.Model):
    class Severity(models.TextChoices):
        LOW = 'LOW', 'Low'
        MEDIUM = 'MEDIUM', 'Medium'
        HIGH = 'HIGH', 'High'

    inspection = models.ForeignKey(
        Inspection,
        on_delete=models.CASCADE,
        related_name='observations_list'
    )
    category = models.CharField(max_length=100)
    description = models.TextField()
    severity = models.CharField(
        max_length=20,
        choices=Severity.choices,
        default=Severity.MEDIUM
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='recorded_observations'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'nis_inspection_observation'
        ordering = ['-created_at']
        verbose_name = 'Inspection Observation'
        verbose_name_plural = 'Inspection Observations'

    def __str__(self):
        return f"[{self.severity}] {self.category} ({self.inspection.claim.claim_number})"


# --- Survey Type Specific Detail Models ---

class FireClaimDetails(models.Model):
    claim = models.OneToOneField(
        'claims.Claim',
        on_delete=models.CASCADE,
        related_name='fire_details'
    )
    construction_details = models.TextField()
    occupancy = models.CharField(max_length=255)
    building_description = models.TextField()
    fire_protection_details = models.TextField(blank=True)
    fire_brigade_informed = models.BooleanField(default=False)
    fire_brigade_details = models.TextField(blank=True)
    police_informed = models.BooleanField(default=False)
    police_details = models.TextField(blank=True)
    fire_cause = models.TextField(blank=True)
    cause_established = models.BooleanField(default=False)
    point_of_origin = models.CharField(max_length=255, blank=True)
    storage_details = models.TextField(blank=True)
    machinery_details = models.TextField(blank=True)
    stock_details = models.TextField(blank=True)
    salvage_observation = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'nis_fire_claim_details'
        verbose_name = 'Fire Claim Details'
        verbose_name_plural = 'Fire Claim Details'

    def __str__(self):
        return f"Fire Details for Claim {self.claim.claim_number}"


class EngineeringClaimDetails(models.Model):
    claim = models.OneToOneField(
        'claims.Claim',
        on_delete=models.CASCADE,
        related_name='engineering_details'
    )
    equipment_name = models.CharField(max_length=255)
    manufacturer = models.CharField(max_length=255, blank=True)
    model = models.CharField(max_length=150, blank=True)
    serial_number = models.CharField(max_length=150, blank=True)
    year_of_manufacture = models.PositiveIntegerField(null=True, blank=True)
    installation_date = models.DateField(null=True, blank=True)
    machine_location = models.CharField(max_length=255, blank=True)
    breakdown_description = models.TextField()
    damage_description = models.TextField()
    cause_of_breakdown = models.TextField(blank=True)
    repair_estimate = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    replacement_cost = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    parts_cost = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    labour_cost = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    testing_cost = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    salvage = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'nis_engineering_claim_details'
        verbose_name = 'Engineering Claim Details'
        verbose_name_plural = 'Engineering Claim Details'

    def __str__(self):
        return f"Engineering Details for Claim {self.claim.claim_number} ({self.equipment_name})"


class MarineClaimDetails(models.Model):
    claim = models.OneToOneField(
        'claims.Claim',
        on_delete=models.CASCADE,
        related_name='marine_details'
    )
    vessel_name = models.CharField(max_length=255)
    voyage_number = models.CharField(max_length=100, blank=True)
    port_of_loading = models.CharField(max_length=150)
    port_of_discharge = models.CharField(max_length=150)
    place_of_survey = models.CharField(max_length=255)
    cargo_description = models.TextField()
    consignor = models.CharField(max_length=255, blank=True)
    consignee = models.CharField(max_length=255, blank=True)
    carrier = models.CharField(max_length=255, blank=True)
    bill_of_lading_number = models.CharField(max_length=100, blank=True)
    container_number = models.CharField(max_length=100, blank=True)
    package_count = models.PositiveIntegerField(null=True, blank=True)
    damage_description = models.TextField()
    transit_details = models.TextField(blank=True)
    packing_condition = models.TextField(blank=True)
    salvage_details = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'nis_marine_claim_details'
        verbose_name = 'Marine Claim Details'
        verbose_name_plural = 'Marine Claim Details'

    def __str__(self):
        return f"Marine Details for Claim {self.claim.claim_number} (Vessel: {self.vessel_name})"


class PropertyClaimDetails(models.Model):
    claim = models.OneToOneField(
        'claims.Claim',
        on_delete=models.CASCADE,
        related_name='property_details'
    )
    property_type = models.CharField(max_length=150)
    occupancy = models.CharField(max_length=255)
    construction_type = models.CharField(max_length=150, blank=True)
    building_area = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    number_of_floors = models.PositiveIntegerField(null=True, blank=True)
    building_description = models.TextField(blank=True)
    contents_description = models.TextField(blank=True)
    stock_description = models.TextField(blank=True)
    damage_description = models.TextField()
    repair_estimate = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    replacement_cost = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    salvage = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'nis_property_claim_details'
        verbose_name = 'Property Claim Details'
        verbose_name_plural = 'Property Claim Details'

    def __str__(self):
        return f"Property Details for Claim {self.claim.claim_number} ({self.property_type})"
