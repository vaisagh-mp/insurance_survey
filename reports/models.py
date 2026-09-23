from decimal import Decimal
from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_logs'
    )
    claim = models.ForeignKey(
        'claims.Claim',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='audit_logs'
    )
    action = models.CharField(max_length=100)
    model_name = models.CharField(max_length=100)
    object_id = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        db_table = 'nis_audit_log'
        ordering = ['-timestamp']
        verbose_name = 'Audit Log'
        verbose_name_plural = 'Audit Logs'
        indexes = [
            models.Index(fields=['claim']),
            models.Index(fields=['model_name', 'object_id']),
            models.Index(fields=['action']),
            models.Index(fields=['timestamp']),
        ]

    def __str__(self):
        actor = self.user.username if self.user else "System"
        return f"[{self.timestamp:%Y-%m-%d %H:%M}] {actor} - {self.action} ({self.model_name} #{self.object_id})"


class ReportStatus(models.TextChoices):
    DRAFT = 'DRAFT', 'Draft'
    SUBMITTED = 'SUBMITTED', 'Submitted'
    QUERY = 'QUERY', 'Query'
    REVISION_REQUIRED = 'REVISION_REQUIRED', 'Revision Required'
    FINAL = 'FINAL', 'Final'


class BaseReport(models.Model):
    claim = models.ForeignKey(
        'claims.Claim',
        on_delete=models.CASCADE,
        related_name='%(class)s_reports'
    )
    report_number = models.CharField(max_length=100, unique=True)
    report_date = models.DateField()
    status = models.CharField(
        max_length=30,
        choices=ReportStatus.choices,
        default=ReportStatus.DRAFT
    )
    version_number = models.PositiveIntegerField(default=1)
    prepared_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='%(class)s_prepared'
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ['-report_date', '-created_at']

    def save(self, *args, **kwargs):
        if not self.report_number:
            from reports.services import generate_report_number
            report_type = self.__class__.__name__
            self.report_number = generate_report_number(self.claim, report_type)
        super().save(*args, **kwargs)


class ILA(BaseReport):
    """Immediate Loss Advice (ILA) report."""
    instruction_date = models.DateField()
    instruction_source = models.CharField(max_length=255)
    surveyor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        limit_choices_to={'role': 'SURVEYOR'},
        related_name='ila_surveys'
    )
    visit_date = models.DateField()
    visit_start_time = models.TimeField()
    visit_end_time = models.TimeField()
    inspection_location = models.CharField(max_length=255)
    person_contacted = models.CharField(max_length=150)
    contact_number = models.CharField(max_length=30)
    contact_email = models.EmailField(blank=True)
    reason_for_delay = models.TextField(blank=True)

    # Policy & Sum Insured Details
    policy_number = models.CharField(max_length=100)
    policy_type = models.CharField(max_length=100)
    policy_period = models.CharField(max_length=100, blank=True)
    commodity = models.CharField(max_length=255)
    sum_insured = models.DecimalField(max_digits=15, decimal_places=2)
    policy_excess = models.DecimalField(max_digits=15, decimal_places=2)

    # Damage Assessment & Estimates
    survey_and_inspection = models.TextField()
    extent_of_damage = models.TextField()
    cause_of_damage = models.TextField()
    salvage_prospect = models.TextField()
    estimated_loss = models.DecimalField(max_digits=15, decimal_places=2)
    claimed_amount = models.DecimalField(max_digits=15, decimal_places=2)
    policy_liability = models.TextField()
    budgetary_reserve = models.DecimalField(max_digits=15, decimal_places=2)
    remarks = models.TextField(blank=True)

    class Meta(BaseReport.Meta):
        db_table = 'nis_ila'
        verbose_name = 'Immediate Loss Advice (ILA)'
        verbose_name_plural = 'Immediate Loss Advices (ILAs)'

    def __str__(self):
        return f"ILA {self.report_number} - Claim {self.claim.claim_number} ({self.get_status_display()})"


class ISR(BaseReport):
    """Initial Survey Report (ISR) / Interim Survey Report."""
    introduction = models.TextField()
    occurrence_details = models.TextField()
    survey_details = models.TextField()
    extent_of_damage = models.TextField()
    cause_of_loss = models.TextField()
    initial_assessment = models.TextField()
    policy_liability = models.TextField()
    documents_received = models.TextField(blank=True)
    documents_pending = models.TextField(blank=True)
    remarks = models.TextField(blank=True)
    recommendation = models.TextField(blank=True)

    class Meta(BaseReport.Meta):
        db_table = 'nis_isr'
        verbose_name = 'Initial Survey Report (ISR)'
        verbose_name_plural = 'Initial Survey Reports (ISRs)'

    def __str__(self):
        return f"ISR {self.report_number} - Claim {self.claim.claim_number} ({self.get_status_display()})"


class FSR(BaseReport):
    """Final Survey Report (FSR)."""

    # Constant disclaimer note to be rendered on reports and PDF outputs
    DISCLAIMER_NOTE = "Subject to the terms and conditions of the insurance policy and final insurer decision"

    introduction = models.TextField()
    occurrence_details = models.TextField()
    survey_details = models.TextField()
    extent_of_loss = models.TextField()
    cause_of_loss = models.TextField()
    adequacy_of_sum_insured = models.TextField(blank=True)

    # Financial & Risk Parameters
    value_at_risk = models.DecimalField(max_digits=15, decimal_places=2)
    sum_insured = models.DecimalField(max_digits=15, decimal_places=2)
    underinsurance_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00')
    )
    salvage_description = models.TextField(blank=True)
    salvage_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00')
    )

    # Coverage & Liability Findings
    insured_claim_description = models.TextField()
    admissibility = models.TextField()
    policy_coverage = models.TextField(blank=True)
    policy_exclusions = models.TextField(blank=True)
    breach_of_warranty = models.BooleanField(default=False)
    warranty_details = models.TextField(blank=True)
    remarks = models.TextField(blank=True)
    final_opinion = models.TextField()
    approved_at = models.DateTimeField(null=True, blank=True)

    # Linked Assessment - Financials read from here
    assessment = models.ForeignKey(
        'assessments.Assessment',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='fsr_reports',
        help_text="Financial assessment figures are linked from here rather than re-typed."
    )

    class Meta(BaseReport.Meta):
        db_table = 'nis_fsr'
        verbose_name = 'Final Survey Report (FSR)'
        verbose_name_plural = 'Final Survey Reports (FSRs)'

    @property
    def gross_assessed_loss(self):
        """Read gross loss directly from linked Assessment if available."""
        return self.assessment.gross_assessed_loss if self.assessment else None

    @property
    def net_assessed_loss(self):
        """Read net assessed loss directly from linked Assessment if available."""
        return self.assessment.net_assessed_loss if self.assessment else None

    def __str__(self):
        return f"FSR {self.report_number} - Claim {self.claim.claim_number} ({self.get_status_display()})"
