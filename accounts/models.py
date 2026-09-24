from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models


class CustomUserManager(UserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault('role', 'ADMIN')
        return super().create_superuser(username, email, password, **extra_fields)


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

    objects = CustomUserManager()

    @property
    def is_admin_role(self):
        return self.role == self.Role.ADMIN or self.is_superuser

    @property
    def is_surveyor_role(self):
        return self.role == self.Role.SURVEYOR and not self.is_superuser

    def save(self, *args, **kwargs):
        if self.is_superuser and self.role != self.Role.ADMIN:
            self.role = self.Role.ADMIN
        super().save(*args, **kwargs)

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
