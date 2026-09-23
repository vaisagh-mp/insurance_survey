from django.contrib import admin
from .models import (
    SurveyType,
    Inspection,
    InspectionPhoto,
    InspectionObservation,
    FireClaimDetails,
    EngineeringClaimDetails,
    MarineClaimDetails,
    PropertyClaimDetails,
)


class InspectionPhotoInline(admin.TabularInline):
    model = InspectionPhoto
    extra = 1
    fields = ('image', 'category', 'caption', 'latitude', 'longitude', 'captured_at', 'uploaded_by')


class InspectionObservationInline(admin.TabularInline):
    model = InspectionObservation
    extra = 1
    fields = ('category', 'description', 'severity', 'created_by')


@admin.register(SurveyType)
class SurveyTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'is_active', 'created_at', 'updated_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'code', 'description')
    ordering = ('name',)


@admin.register(Inspection)
class InspectionAdmin(admin.ModelAdmin):
    list_display = (
        'claim',
        'surveyor',
        'inspection_date',
        'start_time',
        'end_time',
        'location',
        'person_contacted',
        'status',
    )
    list_filter = ('status', 'inspection_date', 'surveyor')
    search_fields = (
        'claim__claim_number',
        'location',
        'person_contacted',
        'contact_number',
        'surveyor__username',
        'surveyor__first_name',
        'surveyor__last_name',
    )
    ordering = ('-inspection_date', '-start_time')
    inlines = [InspectionPhotoInline, InspectionObservationInline]


@admin.register(InspectionPhoto)
class InspectionPhotoAdmin(admin.ModelAdmin):
    list_display = ('inspection', 'category', 'caption', 'uploaded_by', 'created_at')
    list_filter = ('category', 'created_at')
    search_fields = ('caption', 'inspection__claim__claim_number', 'uploaded_by__username')
    ordering = ('-created_at',)


@admin.register(InspectionObservation)
class InspectionObservationAdmin(admin.ModelAdmin):
    list_display = ('inspection', 'category', 'severity', 'created_by', 'created_at')
    list_filter = ('severity', 'category', 'created_at')
    search_fields = ('category', 'description', 'inspection__claim__claim_number', 'created_by__username')
    ordering = ('-created_at',)


@admin.register(FireClaimDetails)
class FireClaimDetailsAdmin(admin.ModelAdmin):
    list_display = ('claim', 'occupancy', 'fire_brigade_informed', 'police_informed', 'cause_established', 'created_at')
    list_filter = ('fire_brigade_informed', 'police_informed', 'cause_established')
    search_fields = ('claim__claim_number', 'occupancy', 'point_of_origin', 'fire_cause')
    ordering = ('-created_at',)


@admin.register(EngineeringClaimDetails)
class EngineeringClaimDetailsAdmin(admin.ModelAdmin):
    list_display = ('claim', 'equipment_name', 'manufacturer', 'year_of_manufacture', 'repair_estimate', 'created_at')
    list_filter = ('manufacturer', 'year_of_manufacture')
    search_fields = ('claim__claim_number', 'equipment_name', 'manufacturer', 'serial_number')
    ordering = ('-created_at',)


@admin.register(MarineClaimDetails)
class MarineClaimDetailsAdmin(admin.ModelAdmin):
    list_display = ('claim', 'vessel_name', 'voyage_number', 'port_of_loading', 'port_of_discharge', 'created_at')
    list_filter = ('port_of_loading', 'port_of_discharge')
    search_fields = ('claim__claim_number', 'vessel_name', 'voyage_number', 'bill_of_lading_number', 'container_number')
    ordering = ('-created_at',)


@admin.register(PropertyClaimDetails)
class PropertyClaimDetailsAdmin(admin.ModelAdmin):
    list_display = ('claim', 'property_type', 'occupancy', 'building_area', 'repair_estimate', 'created_at')
    list_filter = ('property_type',)
    search_fields = ('claim__claim_number', 'property_type', 'occupancy')
    ordering = ('-created_at',)
