from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = 'ADMIN', 'Admin'
        SURVEYOR = 'SURVEYOR', 'Surveyor'

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.SURVEYOR,
        help_text="Designates the user role within the system."
    )

    @property
    def is_admin_role(self):
        return self.role == self.Role.ADMIN

    @property
    def is_surveyor_role(self):
        return self.role == self.Role.SURVEYOR

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"

    class Meta:
        db_table = 'nis_user'


class SurveyorProfile(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='surveyor_profile'
    )
    license_number = models.CharField(max_length=100, unique=True)
    license_expiry = models.DateField()
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    specialization = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'nis_surveyor_profile'
        verbose_name = "Surveyor Profile"
        verbose_name_plural = "Surveyor Profiles"
        ordering = ['-created_at']

    def __str__(self):
        return f"Surveyor: {self.user.get_full_name() or self.user.username} (Lic: {self.license_number})"
