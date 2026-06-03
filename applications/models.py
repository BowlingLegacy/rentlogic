from django.conf import settings
from django.db import models


class HousingApplication(models.Model):
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("submitted", "Submitted"),
        ("approved", "Approved"),
        ("denied", "Denied"),
        ("onboarding", "Onboarding"),
        ("active", "Active Tenant"),
    ]

    property = models.ForeignKey(
        "properties.Property",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="applications",
    )
    applicant_user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="housing_application",
    )
    onboarding_invite = models.OneToOneField(
        "accounts.InviteCode",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_application",
    )

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="submitted")
    full_name = models.CharField(max_length=255)
    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
    age = models.PositiveIntegerField()

    space_type = models.CharField(max_length=50, blank=True)
    space_label = models.CharField(max_length=50, blank=True)

    monthly_rent = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    rent_due_day = models.IntegerField(default=1)
    lease_start_date = models.DateField(blank=True, null=True)

    deposit_required = models.DecimalField(max_digits=10, decimal_places=2, default=450.00)
    deposit_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    utility_monthly = models.DecimalField(max_digits=10, decimal_places=2, default=66.00)
    utility_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    current_address = models.CharField(max_length=255, blank=True)
    current_address_length = models.CharField(max_length=100, blank=True)
    previous_address_1 = models.CharField(max_length=255, blank=True)
    previous_address_1_length = models.CharField(max_length=100, blank=True)
    previous_address_2 = models.CharField(max_length=255, blank=True)
    previous_address_2_length = models.CharField(max_length=100, blank=True)
    previous_address_3 = models.CharField(max_length=255, blank=True)
    previous_address_3_length = models.CharField(max_length=100, blank=True)

    drivers_license_number = models.CharField(max_length=100, blank=True)
    has_valid_odl = models.BooleanField(default=False)
    oregon_id_number = models.CharField(max_length=100, blank=True)
    id_upload = models.FileField(upload_to="application_ids/", blank=True, null=True)

    income_source = models.CharField(max_length=255, blank=True)
    monthly_income = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    employer_name = models.CharField(max_length=255, blank=True)
    employment_length = models.CharField(max_length=100, blank=True)

    previous_evictions = models.TextField(blank=True)
    in_recovery = models.BooleanField(default=False)
    drug_of_choice = models.CharField(max_length=255, blank=True)
    on_parole = models.BooleanField(default=False)
    parole_officer_name = models.CharField(max_length=255, blank=True)
    parole_officer_phone = models.CharField(max_length=50, blank=True)
    felony_history = models.TextField(blank=True)
    odoc_time_served = models.BooleanField(default=False)

    reference_1_name = models.CharField(max_length=255, blank=True)
    reference_1_phone = models.CharField(max_length=50, blank=True)
    reference_1_relationship = models.CharField(max_length=255, blank=True)
    reference_1_type = models.CharField(max_length=100, blank=True)
    reference_2_name = models.CharField(max_length=255, blank=True)
    reference_2_phone = models.CharField(max_length=50, blank=True)
    reference_2_relationship = models.CharField(max_length=255, blank=True)
    reference_2_type = models.CharField(max_length=100, blank=True)

    housing_need = models.TextField(blank=True)
    additional_notes = models.TextField(blank=True)
    sobriety_acknowledgment = models.BooleanField(default=False)
    unconditional_regard_acknowledgment = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def deposit_balance(self):
        remaining = self.deposit_required - self.deposit_paid
        return max(remaining, 0)

    def __str__(self):
        return self.full_name
