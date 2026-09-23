from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, SurveyorProfile


class SurveyorProfileInline(admin.StackedInline):
    model = SurveyorProfile
    can_delete = False
    verbose_name_plural = 'Surveyor Profile'
    fk_name = 'user'
    extra = 0


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    inlines = (SurveyorProfileInline,)
    list_display = ('username', 'email', 'first_name', 'last_name', 'role', 'is_staff', 'is_active')
    list_filter = ('role', 'is_staff', 'is_superuser', 'is_active')
    search_fields = ('username', 'first_name', 'last_name', 'email')
    ordering = ('username',)
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Role Information', {'fields': ('role',)}),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('Role Information', {'fields': ('role',)}),
    )


@admin.register(SurveyorProfile)
class SurveyorProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'license_number', 'license_expiry', 'phone', 'specialization', 'created_at')
    list_filter = ('specialization', 'license_expiry')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'license_number', 'phone')
    ordering = ('-created_at',)
