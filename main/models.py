from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from decimal import Decimal
import random
import string


class BlogPost(models.Model):
    property = models.ForeignKey(
        "Property",
        on_delete=models.CASCADE,
        related_name="blog_posts",
        null=True,
        blank=True,
    )
    author = models.ForeignKey(
        "User",
        on_delete=models.SET_NULL,
        related_name="blog_posts",
        null=True,
        blank=True,
    )
    title = models.CharField(max_length=255)
    body = models.TextField()
    image = models.ImageField(upload_to="blog_images/", blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class BlogComment(models.Model):
    post = models.ForeignKey("BlogPost", on_delete=models.CASCADE, related_name="comments")
    name = models.CharField(max_length=100)
    email = models.EmailField(blank=True)
    comment = models.TextField()
    approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Comment by {self.name} on {self.post.title}"


class User(AbstractUser):
    ROLE_CHOICES = [
        ("tenant", "Tenant / Applicant"),
        ("property_owner", "Property Owner"),
        ("landlord", "Landlord / Property Manager"),
        ("assistant", "Assistant"),
        ("admin", "Platform Admin"),
    ]

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="tenant")
    invite_code = models.CharField(max_length=6, blank=True, null=True, unique=True)
    invite_code_created_at = models.DateTimeField(blank=True, null=True)
    invite_code_used_at = models.DateTimeField(blank=True, null=True)

    def save(self, *args, **kwargs):
        if self.role in ["tenant", "property_owner"]:
            self.is_staff = False
            self.is_superuser = False

        super().save(*args, **kwargs)

    @classmethod
    def generate_unique_code(cls):
        while True:
            code = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
            if not cls.objects.filter(invite_code=code).exists():
                return code

    def refresh_invite_code(self):
        self.invite_code = self.generate_unique_code()
        self.invite_code_created_at = timezone.now()
        self.invite_code_used_at = None
        self.save(update_fields=["invite_code", "invite_code_created_at", "invite_code_used_at"])

    def invite_code_is_valid(self):
        if not self.invite_code or self.invite_code_used_at or not self.invite_code_created_at:
            return False

        return timezone.now() <= self.invite_code_created_at + timezone.timedelta(minutes=30)

    def mark_invite_code_used(self):
        self.invite_code_used_at = timezone.now()
        self.invite_code = None
        self.save(update_fields=["invite_code", "invite_code_used_at"])

    def __str__(self):
        return self.username


class Property(models.Model):
    LEASE_TYPE_CHOICES = [
        ("month_to_month", "Month to Month"),
        ("lease", "Lease"),
    ]
    MOVE_IN_COST_CHOICES = [
        ("rent_deposit", "Rent + Deposit"),
        ("first_last_deposit", "First Month + Last Month + Deposit"),
        ("other", "Other"),
    ]

    name = models.CharField(max_length=255)
    address = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    photo = models.ImageField(upload_to="property_photos/", blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    owner_email = models.EmailField(blank=True)
    landlord_email = models.EmailField(
        blank=True,
        help_text="Login email for the landlord or property manager assigned to this property.",
    )

    unit_size = models.CharField(max_length=100, blank=True)
    cable_ready = models.BooleanField(default=True)
    available_date = models.DateField(blank=True, null=True)
    deposit_amount = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    rent_amount = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    lease_type = models.CharField(max_length=30, choices=LEASE_TYPE_CHOICES, default="month_to_month", blank=True)
    move_in_cost_type = models.CharField(
        max_length=30,
        choices=MOVE_IN_COST_CHOICES,
        default="rent_deposit",
        blank=True,
    )
    move_in_cost_notes = models.CharField(
        max_length=255,
        blank=True,
        help_text="Use for other move-in cost formulas or instructions.",
    )
    utilities_cost = models.CharField(max_length=255, blank=True)
    charges_application_fee = models.BooleanField(default=False)
    application_fee_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"), blank=True)
    application_fee_notes = models.CharField(max_length=255, blank=True)
    requires_background_check = models.BooleanField(default=False)
    background_check_fee_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"), blank=True)
    background_check_instructions = models.TextField(blank=True)
    screening_provider_name = models.CharField(max_length=255, blank=True)
    screening_provider_cost = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"), blank=True)
    screening_admin_fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        blank=True,
        help_text="Optional client-facing admin fee. Do not charge renters on Rental Ledger Pro's behalf.",
    )
    screening_criteria = models.TextField(
        blank=True,
        help_text="Written applicant screening criteria shown to owners and used for consistent review.",
    )
    screening_fee_disclosure = models.TextField(
        blank=True,
        help_text="Property-specific fee and screening disclosure shown before application submission.",
    )
    renters_insurance_provider_name = models.CharField(max_length=255, blank=True, default="Progressive Renters Insurance")
    renters_insurance_url = models.URLField(blank=True, default="https://www.progressive.com/renters/")
    renters_insurance_notes = models.TextField(blank=True)

    AVAILABILITY_CHOICES = [
        ("available", "Available Now"),
        ("waitlist", "Waitlist Open"),
        ("full", "Currently Full"),
    ]

    availability_status = models.CharField(max_length=20, choices=AVAILABILITY_CHOICES, default="full")
    availability_message = models.CharField(max_length=255, default="Join Waitlist for Availability")

    def __str__(self):
        return self.name


class PropertyImage(models.Model):
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="property_gallery/")
    caption = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return f"{self.property.name} Image"


class RentalListing(models.Model):
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("published", "Published"),
        ("paused", "Paused"),
        ("filled", "Filled"),
        ("archived", "Archived"),
    ]

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="rental_listings")
    unit_label = models.CharField(max_length=80, blank=True)
    headline = models.CharField(max_length=180)
    rent_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    deposit_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    utilities_description = models.CharField(max_length=255, blank=True)
    lease_terms = models.CharField(max_length=255, blank=True)
    available_date = models.DateField(blank=True, null=True)
    bedrooms = models.CharField(max_length=50, blank=True)
    bathrooms = models.CharField(max_length=50, blank=True)
    square_feet = models.PositiveIntegerField(blank=True, null=True)
    unit_layout_description = models.TextField(blank=True)
    property_benefits = models.TextField(blank=True)
    amenities = models.TextField(blank=True)
    screening_summary = models.TextField(blank=True)
    listing_body = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_rental_listings")
    published_at = models.DateTimeField(blank=True, null=True)
    filled_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return self.headline


class RentalListingPhoto(models.Model):
    listing = models.ForeignKey(RentalListing, on_delete=models.CASCADE, related_name="photos")
    image = models.ImageField(upload_to="rental_listing_photos/")
    caption = models.CharField(max_length=255, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.caption or f"{self.listing.headline} photo"


class RentalListingChannel(models.Model):
    CHANNEL_CHOICES = [
        ("rental_ledger", "Rental Ledger Pro Public Listing"),
        ("facebook_marketplace", "Facebook Marketplace"),
        ("craigslist", "Craigslist"),
        ("zillow", "Zillow Rental Network"),
        ("apartments_com", "Apartments.com"),
        ("yard_sign", "Yard Sign / QR Code"),
        ("other", "Other"),
    ]

    STATUS_CHOICES = [
        ("not_started", "Not Started"),
        ("ready", "Ready To Post"),
        ("posted", "Posted"),
        ("needs_update", "Needs Update"),
        ("removed", "Removed"),
        ("blocked", "Blocked / Not Available"),
    ]

    listing = models.ForeignKey(RentalListing, on_delete=models.CASCADE, related_name="channels")
    channel = models.CharField(max_length=40, choices=CHANNEL_CHOICES)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default="not_started")
    external_url = models.URLField(blank=True)
    notes = models.TextField(blank=True)
    posted_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("listing", "channel")
        ordering = ["channel"]

    def __str__(self):
        return f"{self.listing.headline} - {self.get_channel_display()}"


class PropertyRoomRent(models.Model):
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="room_rents")
    room_unit_label = models.CharField(max_length=50)
    monthly_rent = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    rent_due_day = models.PositiveSmallIntegerField(default=1)
    utility_monthly = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    deposit_required = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    deposit_paid = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["property__name", "room_unit_label"]
        unique_together = ("property", "room_unit_label")

    def __str__(self):
        return f"{self.property.name} {self.room_unit_label} - ${self.monthly_rent}"


class PropertyUtilityVendor(models.Model):
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="utility_vendors")
    service_type = models.CharField(max_length=80)
    provider_name = models.CharField(max_length=255)
    setup_url = models.URLField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["property__name", "sort_order", "service_type", "provider_name"]
        unique_together = ("property", "service_type", "provider_name")

    def __str__(self):
        return f"{self.property.name} - {self.service_type}: {self.provider_name}"


class PropertyOnboardingDocument(models.Model):
    DOCUMENT_TYPE_CHOICES = [
        ("application", "Rental Application"),
        ("lease", "Lease Agreement"),
        ("other", "Other Onboarding Document"),
    ]
    CONVERSION_STATUS_CHOICES = [
        ("uploaded", "Uploaded for conversion"),
        ("mapped", "Fillable mapping ready"),
    ]

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="onboarding_documents")
    document_type = models.CharField(max_length=30, choices=DOCUMENT_TYPE_CHOICES)
    title = models.CharField(max_length=255)
    source_file = models.FileField(upload_to="property_onboarding_documents/")
    conversion_status = models.CharField(
        max_length=30,
        choices=CONVERSION_STATUS_CHOICES,
        default="uploaded",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["document_type", "-created_at"]

    def __str__(self):
        return f"{self.property.name} - {self.get_document_type_display()}"


class HousingApplication(models.Model):
    DEPOSIT_PAYMENT_PLAN_CHOICES = [
        ("paid_in_full", "Paid in full at move-in"),
        ("ninety_day_plan", "Three payments over 90 days"),
    ]
    COMMUNICATION_PREFERENCE_CHOICES = [
        ("portal", "Portal Only"),
        ("sms", "SMS Text"),
        ("email", "Email"),
    ]
    RESIDENT_FILE_STATUS_CHOICES = [
        ("active", "Active / Current"),
        ("archived", "Archived / Moved Out"),
        ("unit_file", "Empty Unit File"),
    ]

    property = models.ForeignKey(Property, on_delete=models.SET_NULL, null=True, blank=True, related_name="applications")
    user = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="resident_profile")
    resident_file_status = models.CharField(
        max_length=30,
        choices=RESIDENT_FILE_STATUS_CHOICES,
        default="active",
    )
    move_out_date = models.DateField(blank=True, null=True)
    archived_at = models.DateTimeField(blank=True, null=True)
    archive_notes = models.TextField(blank=True)

    full_name = models.CharField(max_length=255)
    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
    age = models.PositiveIntegerField()
    profile_photo = models.ImageField(upload_to="resident_profile_photos/", blank=True, null=True)
    communication_preference = models.CharField(
        max_length=20,
        choices=COMMUNICATION_PREFERENCE_CHOICES,
        default="portal",
    )
    sms_opted_in = models.BooleanField(default=False)
    sms_opted_in_at = models.DateTimeField(blank=True, null=True)
    sms_opted_out_at = models.DateTimeField(blank=True, null=True)
    sms_phone_verified = models.BooleanField(default=False)

    space_type = models.CharField(max_length=50, blank=True)
    space_label = models.CharField(max_length=50, blank=True)

    monthly_rent = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    rent_due_day = models.IntegerField(default=1)
    lease_start_date = models.DateField(blank=True, null=True)
    move_in_rent_charge = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    move_in_utility_charge = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))

    deposit_required = models.DecimalField(max_digits=10, decimal_places=2, default=450.00)
    deposit_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    deposit_payment_plan = models.CharField(
        max_length=30,
        choices=DEPOSIT_PAYMENT_PLAN_CHOICES,
        default="paid_in_full",
    )

    utility_monthly = models.DecimalField(max_digits=10, decimal_places=2, default=66.00)
    utility_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    application_fee_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    application_fee_paid = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    background_check_fee_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    background_check_fee_paid = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    background_check_required = models.BooleanField(default=False)
    background_check_status = models.CharField(
        max_length=30,
        choices=[
            ("not_required", "Not Required"),
            ("pending", "Pending"),
            ("ordered", "Ordered"),
            ("cleared", "Cleared"),
            ("needs_review", "Needs Review"),
            ("declined", "Declined"),
            ("waived", "Waived"),
        ],
        default="not_required",
    )
    screening_consent = models.BooleanField(default=False)
    screening_consent_at = models.DateTimeField(blank=True, null=True)
    screening_provider_name = models.CharField(max_length=255, blank=True)
    background_report = models.FileField(upload_to="background_reports/", blank=True, null=True)
    background_report_received_at = models.DateTimeField(blank=True, null=True)
    screening_score = models.PositiveSmallIntegerField(blank=True, null=True)
    screening_rating = models.CharField(
        max_length=30,
        choices=[
            ("unrated", "Unrated"),
            ("strong", "Strong Candidate"),
            ("qualified", "Qualified"),
            ("review", "Needs Review"),
            ("high_risk", "High Risk"),
            ("declined", "Decline Recommended"),
        ],
        default="unrated",
    )
    screening_review_summary = models.TextField(blank=True)
    owner_final_decision = models.CharField(
        max_length=30,
        choices=[
            ("pending", "Pending Owner Review"),
            ("approved", "Approved"),
            ("approved_conditions", "Approved With Conditions"),
            ("declined", "Declined"),
            ("withdrawn", "Withdrawn"),
        ],
        default="pending",
    )
    owner_decision_notes = models.TextField(blank=True)
    owner_decision_at = models.DateTimeField(blank=True, null=True)

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

    income_source = models.CharField(max_length=255)
    monthly_income = models.DecimalField(max_digits=10, decimal_places=2)
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

    housing_need = models.TextField()
    additional_notes = models.TextField(blank=True)

    sobriety_acknowledgment = models.BooleanField(default=False)
    unconditional_regard_acknowledgment = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    landlord_reviewed_at = models.DateTimeField(blank=True, null=True)

    def deposit_balance(self):
        remaining = self.deposit_required - self.deposit_paid
        return max(remaining, 0)

    def __str__(self):
        return self.full_name


class ResidentUtilitySetup(models.Model):
    application = models.ForeignKey(HousingApplication, on_delete=models.CASCADE, related_name="utility_setups")
    vendor = models.ForeignKey(PropertyUtilityVendor, on_delete=models.CASCADE, related_name="resident_setups")
    opened_at = models.DateTimeField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["vendor__sort_order", "vendor__service_type", "vendor__provider_name"]
        unique_together = ("application", "vendor")

    @property
    def is_completed(self):
        return bool(self.completed_at)

    def __str__(self):
        return f"{self.application.full_name} - {self.vendor.service_type}"


class ApplicantDocument(models.Model):
    DOCUMENT_TYPE_CHOICES = [
        ("lease", "Lease Agreement"),
        ("application_pdf", "Application PDF"),
        ("screening_criteria", "Screening Criteria"),
        ("background_report", "Background Report"),
        ("adverse_action_notice", "Adverse Action Notice"),
        ("id", "Identification"),
        ("income", "Proof of Income"),
        ("bank", "Bank Statement / Deposit Verification"),
        ("onboarding", "Onboarding Document"),
        ("other", "Other"),
    ]

    STATUS_CHOICES = [
        ("uploaded", "Uploaded"),
        ("needs_completion", "Needs Completion"),
        ("needs_signature", "Needs Signature"),
        ("completed", "Completed"),
        ("locked", "Locked Final"),
        ("needs_correction", "Needs Correction"),
    ]
    OCR_STATUS_CHOICES = [
        ("not_processed", "Not Processed"),
        ("extracted", "Text Extracted"),
        ("needs_ocr_provider", "Needs OCR Provider"),
        ("failed", "OCR Failed"),
    ]

    application = models.ForeignKey(HousingApplication, on_delete=models.CASCADE, related_name="documents")
    document_type = models.CharField(max_length=50, choices=DOCUMENT_TYPE_CHOICES, default="other")
    file = models.FileField(upload_to="applicant_documents/")
    name = models.CharField(max_length=255)

    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default="uploaded", blank=True)
    needs_signature = models.BooleanField(default=False)
    needs_initials = models.BooleanField(default=False)
    signed_at = models.DateTimeField(blank=True, null=True)
    submitted_at = models.DateTimeField(blank=True, null=True)
    locked = models.BooleanField(default=False)
    landlord_notified = models.BooleanField(default=False)
    packet_upload = models.BooleanField(default=False)
    packet_reviewed_at = models.DateTimeField(blank=True, null=True)
    packet_reviewed_by = models.ForeignKey(
        "User",
        on_delete=models.SET_NULL,
        related_name="reviewed_tenant_file_packets",
        blank=True,
        null=True,
    )
    packet_notes = models.TextField(blank=True)
    ocr_status = models.CharField(max_length=30, choices=OCR_STATUS_CHOICES, default="not_processed")
    ocr_text = models.TextField(blank=True)
    ocr_error = models.TextField(blank=True)
    ocr_processed_at = models.DateTimeField(blank=True, null=True)
    ocr_suggested_name = models.CharField(max_length=255, blank=True)
    ocr_suggested_unit = models.CharField(max_length=50, blank=True)
    ocr_suggested_date = models.DateField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.status in ["completed", "locked"]:
            self.locked = True

        if self.locked:
            self.status = "locked"

        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.locked:
            return
        super().delete(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.application.full_name})"


class AdverseActionNotice(models.Model):
    ACTION_CHOICES = [
        ("declined", "Application Declined"),
        ("approved_conditions", "Approved With Conditions"),
        ("other", "Other Adverse Action"),
    ]

    application = models.ForeignKey(HousingApplication, on_delete=models.CASCADE, related_name="adverse_action_notices")
    action_type = models.CharField(max_length=30, choices=ACTION_CHOICES, default="declined")
    reasons = models.TextField()
    screening_company_name = models.CharField(max_length=255, blank=True)
    screening_company_contact = models.TextField(blank=True)
    owner_landlord_name = models.CharField(max_length=255, blank=True)
    owner_landlord_contact = models.TextField(blank=True)
    notice_body = models.TextField(blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_adverse_action_notices",
    )
    sent_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.application.full_name} - {self.get_action_type_display()}"


class SignedDocument(models.Model):
    DOCUMENT_TYPE_CHOICES = [
        ("lease", "Resident Lease Agreement"),
        ("emergency_contact", "Emergency Contact Form"),
        ("painted_lady_acknowledgment", "Painted Lady Acknowledgment"),
        ("lead_disclosure", "Lead Disclosure"),
        ("asbestos_disclosure", "Asbestos Disclosure"),
        ("house_rules", "House Rules"),
        ("other", "Other"),
    ]

    application = models.ForeignKey(
        HousingApplication,
        on_delete=models.CASCADE,
        related_name="signed_documents"
    )

    document_type = models.CharField(
        max_length=50,
        choices=DOCUMENT_TYPE_CHOICES,
        default="other"
    )

    title = models.CharField(max_length=255)

    # ---------------------------------------------------------
    # AUTO-POPULATED LEASE FIELDS
    # ---------------------------------------------------------
    property_name = models.CharField(max_length=255, blank=True)
    property_address = models.CharField(max_length=255, blank=True)

    resident_name = models.CharField(max_length=255, blank=True)

    room_space = models.CharField(max_length=100, blank=True)

    monthly_rent = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.00
    )

    utility_fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.00
    )

    security_deposit = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.00
    )

    deposit_payment_plan = models.CharField(
        max_length=30,
        choices=HousingApplication.DEPOSIT_PAYMENT_PLAN_CHOICES,
        default="paid_in_full",
    )

    lease_start_date = models.DateField(blank=True, null=True)

    landlord_name = models.CharField(
        max_length=255,
        default="Michael Bowling"
    )

    landlord_signature = models.CharField(
        max_length=255,
        default="Michael Bowling"
    )

    lease_sent_date = models.DateField(blank=True, null=True)

    # ---------------------------------------------------------
    # RESIDENT ACKNOWLEDGMENTS / INITIALS
    # ---------------------------------------------------------
    rent_initials = models.CharField(max_length=10, blank=True)

    sobriety_initials = models.CharField(max_length=10, blank=True)

    testing_initials = models.CharField(max_length=10, blank=True)

    guest_policy_initials = models.CharField(max_length=10, blank=True)

    cleanliness_initials = models.CharField(max_length=10, blank=True)

    disclosure_initials = models.CharField(max_length=10, blank=True)

    emergency_contact_name = models.CharField(max_length=255, blank=True)
    emergency_contact_phone = models.CharField(max_length=50, blank=True)
    emergency_contact_relationship = models.CharField(max_length=255, blank=True)
    emergency_medical_notes = models.TextField(blank=True)

    # ---------------------------------------------------------
    # SIGNATURES
    # ---------------------------------------------------------
    resident_signature = models.CharField(
        max_length=255,
        blank=True
    )

    signature_agreement = models.BooleanField(default=False)

    signed_at = models.DateTimeField(blank=True, null=True)

    locked = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} - {self.application.full_name}"

    def save(self, *args, **kwargs):

        # AUTO POPULATE FROM RESIDENT FILE
        if self.application:

            self.resident_name = self.application.full_name

            self.monthly_rent = self.application.monthly_rent

            self.utility_fee = self.application.utility_monthly

            self.security_deposit = self.application.deposit_required

            self.deposit_payment_plan = self.application.deposit_payment_plan

            self.room_space = (
                f"{self.application.space_type} "
                f"{self.application.space_label}"
            )

            if self.application.property:
                self.property_name = self.application.property.name
                self.property_address = self.application.property.address

            if self.application.lease_start_date:
                self.lease_start_date = self.application.lease_start_date
            elif not self.lease_start_date:
                self.lease_start_date = timezone.now().date()

        super().save(*args, **kwargs)


class RentHistory(models.Model):
    application = models.ForeignKey(HousingApplication, on_delete=models.CASCADE, related_name="rent_history")
    rent_amount = models.DecimalField(max_digits=10, decimal_places=2)
    effective_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.application.full_name} - ${self.rent_amount}"


class Payment(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    ]

    PAYMENT_TYPE_CHOICES = [
        ("rent", "Rent"),
        ("deposit", "Deposit"),
        ("utility", "Utilities"),
        ("application_fee", "Application Fee"),
        ("background_check_fee", "Background Check Fee"),
        ("late_fee", "Late Fee"),
        ("other", "Other"),
    ]

    PAYMENT_METHOD_CHOICES = [
        ("stripe_card", "Stripe Card"),
        ("stripe_cashapp", "Stripe Cash App Pay"),
        ("bank_transfer", "Bank Transfer"),
        ("cashapp", "Cash App"),
        ("cash", "Cash"),
        ("check", "Check"),
        ("money_order", "Money Order"),
        ("zelle", "Zelle"),
        ("ach", "ACH"),
        ("other", "Other"),
    ]

    application = models.ForeignKey(HousingApplication, on_delete=models.CASCADE, related_name="payments")
    payment_type = models.CharField(max_length=30, choices=PAYMENT_TYPE_CHOICES, default="rent")
    payment_method = models.CharField(max_length=30, choices=PAYMENT_METHOD_CHOICES, default="stripe_card")
    description = models.CharField(max_length=255, blank=True)
    reference_number = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recorded_payments",
    )
    received_at = models.DateTimeField(blank=True, null=True)
    service_month = models.DateField(
        blank=True,
        null=True,
        help_text="First day of the month this payment applies to for rent roll and T-12 reporting.",
    )
    months_covered = models.PositiveSmallIntegerField(default=1)

    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")

    stripe_session_id = models.CharField(max_length=255, blank=True)
    stripe_payment_intent = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def accounting_month(self):
        if self.service_month:
            return self.service_month.replace(day=1)
        if self.received_at:
            return timezone.localtime(self.received_at).date().replace(day=1)
        return timezone.localtime(self.created_at).date().replace(day=1)

    @property
    def accounting_month_label(self):
        return self.accounting_month.strftime("%B %Y")

    def __str__(self):
        return f"{self.application.full_name} - {self.get_payment_type_display()} - ${self.amount} - {self.status}"


class FinancialUpload(models.Model):
    LEDGER_SCOPE_CHOICES = [
        ("property", "Property Ledger"),
        ("company", "Company Ledger"),
        ("bank", "Bank Activity"),
    ]

    property = models.ForeignKey(
        "Property",
        on_delete=models.SET_NULL,
        related_name="financial_uploads",
        blank=True,
        null=True,
    )
    ledger_scope = models.CharField(max_length=30, choices=LEDGER_SCOPE_CHOICES, default="property")
    file = models.FileField(upload_to="financial_uploads/")
    name = models.CharField(max_length=255, default="Financial Upload")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    parsed_at = models.DateTimeField(blank=True, null=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.name} ({self.uploaded_at.date()})"


class ExpenseCategory(models.Model):
    ENTRY_TYPE_CHOICES = [
        ("operating_expense", "Operating Expense"),
        ("debt_service", "Debt Service"),
        ("capital_expense", "Capital Expense"),
        ("other", "Other"),
    ]

    name = models.CharField(max_length=255, unique=True)
    entry_type = models.CharField(max_length=50, choices=ENTRY_TYPE_CHOICES, default="operating_expense")
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        "User",
        on_delete=models.SET_NULL,
        related_name="created_expense_categories",
        blank=True,
        null=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["entry_type", "name"]
        verbose_name_plural = "Expense categories"

    def __str__(self):
        return self.name


class AccountingReceipt(models.Model):
    STATUS_CHOICES = [
        ("needs_review", "Needs Review"),
        ("approved", "Approved"),
        ("ignored", "Ignored / Duplicate"),
    ]

    OCR_STATUS_CHOICES = [
        ("not_processed", "Not Processed"),
        ("extracted", "Text Extracted"),
        ("needs_ocr_provider", "Needs OCR Provider"),
        ("failed", "OCR Failed"),
    ]

    PAYMENT_METHOD_CHOICES = Payment.PAYMENT_METHOD_CHOICES

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="accounting_receipts")
    receipt_file = models.FileField(upload_to="accounting_receipts/")
    vendor = models.CharField(max_length=255, blank=True)
    receipt_date = models.DateField(blank=True, null=True)
    category = models.ForeignKey(
        ExpenseCategory,
        on_delete=models.SET_NULL,
        related_name="receipts",
        blank=True,
        null=True,
    )
    entry_type = models.CharField(
        max_length=50,
        choices=ExpenseCategory.ENTRY_TYPE_CHOICES,
        default="operating_expense",
    )
    description = models.TextField(blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    payment_method = models.CharField(max_length=30, choices=PAYMENT_METHOD_CHOICES, default="other")
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default="needs_review")
    uploaded_by = models.ForeignKey(
        "User",
        on_delete=models.SET_NULL,
        related_name="uploaded_accounting_receipts",
        blank=True,
        null=True,
    )
    reviewed_by = models.ForeignKey(
        "User",
        on_delete=models.SET_NULL,
        related_name="reviewed_accounting_receipts",
        blank=True,
        null=True,
    )
    financial_upload = models.ForeignKey(
        FinancialUpload,
        on_delete=models.SET_NULL,
        related_name="receipt_sources",
        blank=True,
        null=True,
    )
    financial_entry = models.OneToOneField(
        "FinancialEntry",
        on_delete=models.SET_NULL,
        related_name="source_receipt",
        blank=True,
        null=True,
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(blank=True, null=True)
    ocr_status = models.CharField(max_length=30, choices=OCR_STATUS_CHOICES, default="not_processed")
    ocr_text = models.TextField(blank=True)
    ocr_error = models.TextField(blank=True)
    ocr_processed_at = models.DateTimeField(blank=True, null=True)
    ocr_suggested_vendor = models.CharField(max_length=255, blank=True)
    ocr_suggested_date = models.DateField(blank=True, null=True)
    ocr_suggested_amount = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"{self.property.name} - {self.vendor or 'Receipt'} - ${self.amount}"


class PropertyOwnerIntake(models.Model):
    STATUS_CHOICES = [
        ("submitted", "Submitted"),
        ("invited", "Invite Sent"),
        ("registered", "Registered"),
    ]

    LEAD_STAGE_CHOICES = [
        ("new", "New Lead"),
        ("contacted", "Contacted"),
        ("demo_scheduled", "Demo Scheduled"),
        ("onboarding", "Onboarding"),
        ("closed_won", "Closed Won"),
        ("closed_lost", "Closed Lost"),
    ]

    PROPERTY_TYPE_CHOICES = [
        ("multifamily", "Multifamily"),
        ("commercial", "Commercial"),
        ("mixed_use", "Mixed Use"),
        ("single_family", "Single-Family Rentals"),
        ("specialty", "Specialty / Other"),
    ]

    full_name = models.CharField(max_length=255)
    company_name = models.CharField(max_length=255, blank=True)
    email = models.EmailField()
    phone = models.CharField(max_length=50)
    property_count = models.PositiveIntegerField(default=1)
    total_units = models.PositiveIntegerField(default=0)
    property_types = models.CharField(max_length=255, blank=True)
    current_software = models.CharField(max_length=255, blank=True)
    current_pain_points = models.TextField(blank=True)
    migration_notes = models.TextField(blank=True)

    needs_rent_collection = models.BooleanField(default=False)
    needs_accounting = models.BooleanField(default=False)
    needs_owner_reporting = models.BooleanField(default=False)
    needs_data_migration = models.BooleanField(default=False)
    needs_resident_files = models.BooleanField(default=False)
    needs_documents = models.BooleanField(default=False)
    needs_maintenance = models.BooleanField(default=False)
    needs_resident_communication = models.BooleanField(default=False)
    needs_screening = models.BooleanField(default=False)
    needs_property_websites = models.BooleanField(default=False)
    charges_application_fee = models.BooleanField(default=False)
    performs_background_checks = models.BooleanField(default=False)
    advertises_available_units = models.BooleanField(default=False)
    uses_automatic_late_fees = models.BooleanField(default=False)
    needs_custom_reports = models.BooleanField(default=False)
    offers_renters_insurance = models.BooleanField(default=False)
    desired_reports = models.TextField(blank=True)
    tenant_utility_setup_notes = models.TextField(
        blank=True,
        help_text="Utility accounts tenants must set up, with vendor names, links, phones, or notes.",
    )

    onboarding_timeline = models.CharField(max_length=255, blank=True)
    dashboard_goals = models.TextField(blank=True)
    additional_notes = models.TextField(blank=True)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default="submitted")
    lead_stage = models.CharField(max_length=30, choices=LEAD_STAGE_CHOICES, default="new")
    follow_up_date = models.DateField(blank=True, null=True)
    internal_notes = models.TextField(blank=True)
    user = models.ForeignKey(
        "User",
        on_delete=models.SET_NULL,
        related_name="property_owner_intakes",
        blank=True,
        null=True,
    )
    invite_sent_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.full_name} - {self.company_name or self.email}"


class ExistingResidentIntake(models.Model):
    property = models.ForeignKey(
        "Property",
        on_delete=models.CASCADE,
        related_name="existing_resident_intakes",
    )
    application = models.OneToOneField(
        "HousingApplication",
        on_delete=models.SET_NULL,
        related_name="existing_resident_intake",
        blank=True,
        null=True,
    )
    first_name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100)
    email = models.EmailField()
    phone = models.CharField(max_length=50)
    room_unit_label = models.CharField(max_length=50, blank=True)
    profile_photo = models.ImageField(upload_to="existing_resident_intake_photos/", blank=True, null=True)
    sms_opted_in = models.BooleanField(default=False)
    sms_opted_in_at = models.DateTimeField(blank=True, null=True)
    has_valid_odl = models.BooleanField(default=False)
    years_at_residence = models.PositiveIntegerField(default=0)
    move_in_month = models.CharField(max_length=7, blank=True)
    additional_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    landlord_reviewed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]

    def full_name(self):
        return " ".join(part for part in [self.first_name, self.middle_name, self.last_name] if part)

    def __str__(self):
        return f"{self.full_name()} - {self.property.name}"


class CurrentResidentRosterEntry(models.Model):
    property = models.ForeignKey(
        "Property",
        on_delete=models.CASCADE,
        related_name="current_resident_roster_entries",
    )
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    room_unit_label = models.CharField(max_length=50, blank=True)
    monthly_rent = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    rent_due_day = models.PositiveSmallIntegerField(default=1)
    monthly_utilities = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    current_rent_balance = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    current_utility_balance = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    deposit_required = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    deposit_held = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    last_month_rent_paid = models.BooleanField(default=False)
    last_month_rent_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    outstanding_balance = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    is_active = models.BooleanField(default=True)
    uploaded_by = models.ForeignKey(
        "User",
        on_delete=models.SET_NULL,
        related_name="uploaded_current_resident_roster_entries",
        blank=True,
        null=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["property__name", "room_unit_label", "last_name", "first_name"]
        unique_together = ("property", "first_name", "last_name", "email", "room_unit_label")

    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def __str__(self):
        return f"{self.property.name} - {self.full_name()}"


class ReportTemplate(models.Model):
    MATH_MODE_CHOICES = [
        ("none", "No extra math"),
        ("sum", "Sum selected column"),
        ("average", "Average selected column"),
    ]

    name = models.CharField(max_length=120)
    created_by = models.ForeignKey(
        "User",
        on_delete=models.CASCADE,
        related_name="custom_report_templates",
    )
    property = models.ForeignKey(
        "Property",
        on_delete=models.SET_NULL,
        related_name="custom_report_templates",
        blank=True,
        null=True,
    )
    report_type = models.CharField(max_length=80)
    start_date = models.DateField(blank=True, null=True)
    end_date = models.DateField(blank=True, null=True)
    financial_entry_types = models.JSONField(default=list, blank=True)
    math_mode = models.CharField(max_length=20, choices=MATH_MODE_CHOICES, default="none")
    math_column = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        unique_together = ("created_by", "name")

    def __str__(self):
        return self.name

    @property
    def report_type_label(self):
        labels = {
            "resident_phone_list": "Resident Phone List",
            "resident_roster": "Resident Roster",
            "resident_directory": "Resident Directory / Roster Export",
            "unit_rent_setup": "Unit Rent Setup",
            "delinquency_report": "Delinquency Report",
            "deposit_liability": "Deposit Liability Report",
            "payment_summary": "Payment Summary",
            "property_performance_summary": "Property Performance Summary",
            "valuation_estimate": "Valuation Estimate",
            "income_statement": "Income Statement / P&L",
            "expense_by_category": "Expense Detail by Category",
            "vendor_expense": "Vendor Expense Report",
            "occupancy_vacancy": "Occupancy / Vacancy Report",
            "capital_improvement_log": "Capital Improvement Log",
            "utility_cost_trend": "Utility Usage / Cost Trend",
            "insurance_compliance": "Insurance / Compliance Report",
            "financial_entries": "Financial Entries / Expenses",
            "receipt_expense_detail": "Receipt Expense Detail",
            "vendor_directory": "Vendor Directory",
            "vendor_category_summary": "Vendor / Category Summary",
            "data_inventory": "Property Data Inventory",
        }
        return labels.get(self.report_type, self.report_type)


class LandlordIntake(models.Model):
    STATUS_CHOICES = PropertyOwnerIntake.STATUS_CHOICES

    full_name = models.CharField(max_length=255, blank=True)
    company_name = models.CharField(max_length=255, blank=True)
    email = models.EmailField()
    phone = models.CharField(max_length=50, blank=True)
    address = models.CharField(max_length=255, blank=True)
    property_count = models.PositiveIntegerField(default=1)
    total_units = models.PositiveIntegerField(default=0)
    properties_managed = models.TextField(blank=True)
    current_software = models.CharField(max_length=255, blank=True)
    current_pain_points = models.TextField(blank=True)
    migration_notes = models.TextField(blank=True)

    needs_rent_collection = models.BooleanField(default=False)
    needs_applications = models.BooleanField(default=False)
    needs_resident_files = models.BooleanField(default=False)
    needs_documents = models.BooleanField(default=False)
    needs_maintenance = models.BooleanField(default=False)
    needs_resident_communication = models.BooleanField(default=False)
    needs_screening = models.BooleanField(default=False)
    needs_accounting_access = models.BooleanField(default=False)

    dashboard_goals = models.TextField(blank=True)
    additional_notes = models.TextField(blank=True)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default="submitted")
    user = models.ForeignKey(
        "User",
        on_delete=models.SET_NULL,
        related_name="landlord_intakes",
        blank=True,
        null=True,
    )
    invite_sent_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Landlord Invite / Profile"
        verbose_name_plural = "Landlord Invites / Profiles"

    def __str__(self):
        return f"{self.full_name} - {self.company_name or self.email}"


class FinancialEntry(models.Model):
    ENTRY_TYPE_CHOICES = [
        ("income", "Income"),
        ("operating_expense", "Operating Expense"),
        ("debt_service", "Debt Service"),
        ("capital_expense", "Capital Expense"),
        ("other", "Other"),
    ]

    upload = models.ForeignKey(FinancialUpload, on_delete=models.CASCADE, related_name="entries")
    ledger_scope = models.CharField(max_length=30, choices=FinancialUpload.LEDGER_SCOPE_CHOICES, default="property")
    property_name = models.CharField(max_length=255, blank=True, default="Painted Lady")
    sheet_name = models.CharField(max_length=255)
    row_number = models.IntegerField(default=0)

    entry_date = models.DateField(blank=True, null=True)
    month = models.IntegerField(blank=True, null=True)
    year = models.IntegerField(blank=True, null=True)

    entry_type = models.CharField(max_length=50, choices=ENTRY_TYPE_CHOICES, default="other")
    category = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)

    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["year", "month", "entry_type", "category"]

    def __str__(self):
        return f"{self.get_entry_type_display()} - ${self.amount} - {self.sheet_name}"


class ResidentMessage(models.Model):
    MESSAGE_TYPE_CHOICES = [
        ("maintenance", "Maintenance Request"),
        ("complaint", "Complaint"),
        ("general", "General Message"),
        ("document", "Document Question"),
    ]

    STATUS_CHOICES = [
        ("submitted", "Submitted"),
        ("reviewed", "Reviewed"),
        ("closed", "Closed"),
    ]

    application = models.ForeignKey(HousingApplication, on_delete=models.CASCADE, related_name="resident_messages")
    message_type = models.CharField(max_length=30, choices=MESSAGE_TYPE_CHOICES, default="general")
    subject = models.CharField(max_length=255)
    message = models.TextField()
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default="submitted")
    locked = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_message_type_display()} - {self.application.full_name} - {self.created_at}"


class ResidentMessageReply(models.Model):
    message = models.ForeignKey(ResidentMessage, on_delete=models.CASCADE, related_name="replies")
    sender = models.ForeignKey(
        "User",
        on_delete=models.SET_NULL,
        related_name="resident_message_replies",
        blank=True,
        null=True,
    )
    body = models.TextField()
    visible_to_resident = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Reply to {self.message.subject} - {self.created_at}"


class SmsMessageLog(models.Model):
    STATUS_CHOICES = [
        ("not_configured", "Provider Not Configured"),
        ("skipped_no_consent", "Skipped - No Consent"),
        ("queued", "Queued"),
        ("sent", "Sent"),
        ("failed", "Failed"),
    ]

    application = models.ForeignKey(HousingApplication, on_delete=models.CASCADE, related_name="sms_logs")
    resident_message = models.ForeignKey(
        ResidentMessage,
        on_delete=models.SET_NULL,
        related_name="sms_logs",
        blank=True,
        null=True,
    )
    to_phone = models.CharField(max_length=50)
    body = models.TextField()
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default="queued")
    provider_message_id = models.CharField(max_length=255, blank=True)
    error_message = models.TextField(blank=True)
    sent_by = models.ForeignKey(
        "User",
        on_delete=models.SET_NULL,
        related_name="sent_sms_messages",
        blank=True,
        null=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.application.full_name} - {self.get_status_display()}"


class CompanyMailboxConnection(models.Model):
    mailbox_email = models.EmailField(unique=True)
    access_token = models.TextField(blank=True)
    refresh_token = models.TextField(blank=True)
    token_expires_at = models.DateTimeField(blank=True, null=True)
    connected_by = models.ForeignKey(
        "User",
        on_delete=models.SET_NULL,
        related_name="connected_company_mailboxes",
        blank=True,
        null=True,
    )
    connected_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["mailbox_email"]

    @property
    def is_connected(self):
        return bool(self.refresh_token)

    def __str__(self):
        return self.mailbox_email
