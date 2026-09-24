from decimal import Decimal
from django.conf import settings
from django.db import models


class Priority(models.TextChoices):
    LOW = 'LOW', 'Low'
    MEDIUM = 'MEDIUM', 'Medium'
    HIGH = 'HIGH', 'High'


class ClaimStatus(models.TextChoices):
    NEW = 'NEW', 'New'
    ASSIGNED = 'ASSIGNED', 'Assigned'
    INSPECTION_PENDING = 'INSPECTION_PENDING', 'Inspection Pending'
    INSPECTION_COMPLETED = 'INSPECTION_COMPLETED', 'Inspection Completed'
    ILA_PREPARED = 'ILA_PREPARED', 'ILA Prepared'
    LOR_ISSUED = 'LOR_ISSUED', 'LOR Issued'
    DOCUMENT_COLLECTION = 'DOCUMENT_COLLECTION', 'Document Collection'
    ASSESSMENT_IN_PROGRESS = 'ASSESSMENT_IN_PROGRESS', 'Assessment In Progress'
    ISR_PREPARED = 'ISR_PREPARED', 'ISR Prepared'
    FSR_PREPARED = 'FSR_PREPARED', 'FSR Prepared'
    REPORT_SUBMITTED = 'REPORT_SUBMITTED', 'Report Submitted'
    CLOSED = 'CLOSED', 'Closed'
    QUERY_RAISED = 'QUERY_RAISED', 'Query Raised'
    REVISION_REQUIRED = 'REVISION_REQUIRED', 'Revision Required'
    RESUBMITTED = 'RESUBMITTED', 'Resubmitted'
    ON_HOLD = 'ON_HOLD', 'On Hold'
    CANCELLED = 'CANCELLED', 'Cancelled'


class Insurer(models.Model):
    company_name = models.CharField(max_length=255)
    branch_name = models.CharField(max_length=255)
    address = models.TextField()
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    pincode = models.CharField(max_length=20)
    contact_person = models.CharField(max_length=150)
    phone = models.CharField(max_length=30)
    email = models.EmailField()
    gstin = models.CharField(max_length=50, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'nis_insurer'
        ordering = ['company_name', 'branch_name']
        verbose_name = 'Insurer'
        verbose_name_plural = 'Insurers'

    def __str__(self):
        return f"{self.company_name} - {self.branch_name}"


class Insured(models.Model):
    name = models.CharField(max_length=255)
    company_name = models.CharField(max_length=255, blank=True)
    address = models.TextField()
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    pincode = models.CharField(max_length=20)
    phone = models.CharField(max_length=30)
    email = models.EmailField()
    gstin = models.CharField(max_length=50, blank=True)
    contact_person = models.CharField(max_length=150)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'nis_insured'
        ordering = ['name']
        verbose_name = 'Insured'
        verbose_name_plural = 'Insured Parties'

    def __str__(self):
        if self.company_name:
            return f"{self.name} ({self.company_name})"
        return self.name


class Policy(models.Model):
    insurer = models.ForeignKey(
        Insurer,
        on_delete=models.PROTECT,
        related_name='policies'
    )
    policy_number = models.CharField(max_length=100, unique=True)
    policy_type = models.CharField(max_length=100)
    start_datetime = models.DateTimeField()
    end_datetime = models.DateTimeField()
    sum_insured = models.DecimalField(max_digits=15, decimal_places=2)
    excess = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    commodity = models.CharField(max_length=255)
    subject_matter = models.TextField()
    remarks = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'nis_policy'
        ordering = ['-created_at']
        verbose_name = 'Policy'
        verbose_name_plural = 'Policies'

    def __str__(self):
        return f"{self.policy_number} ({self.insurer.company_name})"


class Claim(models.Model):
    claim_number = models.CharField(max_length=50, unique=True, blank=True)
    report_number = models.CharField(max_length=50, blank=True)
    survey_type = models.ForeignKey(
        'surveys.SurveyType',
        on_delete=models.PROTECT,
        related_name='claims'
    )
    insurer = models.ForeignKey(
        Insurer,
        on_delete=models.PROTECT,
        related_name='claims'
    )
    insured = models.ForeignKey(
        Insured,
        on_delete=models.PROTECT,
        related_name='claims'
    )
    policy = models.ForeignKey(
        Policy,
        on_delete=models.PROTECT,
        related_name='claims'
    )
    instruction_date = models.DateField()
    instruction_source = models.CharField(max_length=255)
    date_of_loss = models.DateField()
    nature_of_loss = models.CharField(max_length=255)
    loss_location = models.TextField()
    claimed_amount = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    priority = models.CharField(
        max_length=20,
        choices=Priority.choices,
        default=Priority.MEDIUM
    )
    status = models.CharField(
        max_length=50,
        choices=ClaimStatus.choices,
        default=ClaimStatus.NEW
    )
    claim_description = models.TextField(blank=True)
    contact_person = models.CharField(max_length=150, blank=True)
    contact_phone = models.CharField(max_length=30, blank=True)
    contact_email = models.EmailField(blank=True)
    internal_remarks = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='claims_created'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'nis_claim'
        ordering = ['-created_at']
        verbose_name = 'Claim'
        verbose_name_plural = 'Claims'
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['survey_type']),
        ]

    def save(self, *args, **kwargs):
        is_new = self._state.adding or not self.pk
        if not self.claim_number:
            last_claim = Claim.objects.order_by('-id').first()
            next_id = (last_claim.id + 1) if last_claim and last_claim.id else 1
            generated_number = f"CLM-{next_id:05d}"
            while Claim.objects.filter(claim_number=generated_number).exists():
                next_id += 1
                generated_number = f"CLM-{next_id:05d}"
            self.claim_number = generated_number
        super().save(*args, **kwargs)

        if is_new:
            from reports.services import log_action
            log_action(
                user=self.created_by,
                action="CLAIM_CREATED",
                obj=self,
                description=f"Claim {self.claim_number} created with status {self.status}.",
                claim=self
            )

    def get_survey_details(self):
        """Returns the associated survey-type-specific detail record if present."""
        for attr in ['fire_details', 'engineering_details', 'marine_details', 'property_details']:
            if hasattr(self, attr):
                return getattr(self, attr)
        return None

    @property
    def active_assignment(self):
        """Returns the most recent active (non-reassigned) SurveyAssignment if any."""
        return self.assignments.exclude(status='REASSIGNED').order_by('-assigned_at').first()

    @property
    def current_surveyor(self):
        """Returns the currently assigned surveyor User instance if any."""
        assignment = self.active_assignment
        return assignment.surveyor if assignment else None

    @property
    def latest_submitted_report(self):
        """
        Returns the report instance (ILA, ISR, or FSR) that was most recently submitted
        (status in SUBMITTED or FINAL, ordered by submitted_at desc).
        """
        candidates = []
        for rel in ['ila_reports', 'isr_reports', 'fsr_reports']:
            if hasattr(self, rel):
                rep = getattr(self, rel).filter(status__in=['SUBMITTED', 'FINAL']).order_by('-submitted_at', '-updated_at').first()
                if rep:
                    ts = rep.submitted_at or rep.updated_at
                    candidates.append((ts, rep))
        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            return candidates[0][1]
        return None

    @property
    def latest_submitted_report_type(self):
        """Returns 'ILA', 'ISR', 'FSR', or None."""
        rep = self.latest_submitted_report
        return rep.__class__.__name__.upper() if rep else None

    @property
    def status_display_with_stage(self):
        """
        Returns e.g. 'Report Submitted (ILA)' if status == REPORT_SUBMITTED and report exists,
        otherwise standard get_status_display().
        """
        if self.status == ClaimStatus.REPORT_SUBMITTED:
            stage = self.latest_submitted_report_type
            if stage:
                return f"Report Submitted ({stage})"
        return self.get_status_display()

    @property
    def has_completed_lor_and_assessment(self):
        """
        Returns True if the claim has completed both LOR and Assessment stages,
        either by passing through the statuses or by having actual LOR requirements and Assessment data created.
        """
        hist = self.status_history.all()
        has_lor = hist.filter(new_status=ClaimStatus.LOR_ISSUED).exists() or self.requirements.exists()
        has_assessment = hist.filter(new_status=ClaimStatus.ASSESSMENT_IN_PROGRESS).exists() or hasattr(self, 'assessment')
        return bool(has_lor and has_assessment)

    def __str__(self):
        return f"{self.claim_number} - {self.insured.name}"


class ClaimStatusHistory(models.Model):
    claim = models.ForeignKey(
        Claim,
        on_delete=models.CASCADE,
        related_name='status_history'
    )
    old_status = models.CharField(
        max_length=50,
        choices=ClaimStatus.choices
    )
    new_status = models.CharField(
        max_length=50,
        choices=ClaimStatus.choices
    )
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='claim_status_changes'
    )
    changed_at = models.DateTimeField(auto_now_add=True)
    remarks = models.TextField(blank=True)

    class Meta:
        db_table = 'nis_claim_status_history'
        ordering = ['-changed_at']
        verbose_name = 'Claim Status History'
        verbose_name_plural = 'Claim Status Histories'

    def __str__(self):
        return f"{self.claim.claim_number}: {self.old_status} -> {self.new_status} by {self.changed_by.username}"


class SurveyAssignment(models.Model):
    class Status(models.TextChoices):
        ASSIGNED = 'ASSIGNED', 'Assigned'
        IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
        COMPLETED = 'COMPLETED', 'Completed'
        REASSIGNED = 'REASSIGNED', 'Reassigned'

    claim = models.ForeignKey(
        Claim,
        on_delete=models.CASCADE,
        related_name='assignments'
    )
    surveyor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        limit_choices_to={'role': 'SURVEYOR'},
        related_name='survey_assignments'
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='assignments_given'
    )
    assigned_at = models.DateTimeField(auto_now_add=True)
    due_date = models.DateField()
    priority = models.CharField(
        max_length=20,
        choices=Priority.choices,
        default=Priority.MEDIUM
    )
    instructions = models.TextField(blank=True)
    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.ASSIGNED
    )
    remarks = models.TextField(blank=True)

    class Meta:
        db_table = 'nis_survey_assignment'
        ordering = ['-assigned_at']
        verbose_name = 'Survey Assignment'
        verbose_name_plural = 'Survey Assignments'

    def save(self, *args, **kwargs):
        is_new = self._state.adding or not self.pk
        super().save(*args, **kwargs)

        from reports.services import log_action
        if is_new:
            log_action(
                user=self.assigned_by,
                action="SURVEYOR_ASSIGNED",
                obj=self,
                description=f"Surveyor {self.surveyor.username} assigned to claim {self.claim.claim_number}.",
                claim=self.claim
            )
        else:
            log_action(
                user=self.assigned_by,
                action="SURVEYOR_REASSIGNED",
                obj=self,
                description=f"Survey assignment #{self.id} updated/reassigned for surveyor {self.surveyor.username} on claim {self.claim.claim_number}.",
                claim=self.claim
            )

    def __str__(self):
        return f"Assignment {self.claim.claim_number} -> {self.surveyor.get_full_name() or self.surveyor.username}"
