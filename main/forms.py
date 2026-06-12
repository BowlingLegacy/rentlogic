from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import (
    HousingApplication,
    User,
    BlogComment,
    FinancialUpload,
    ResidentMessage,
    ApplicantDocument,
    Property,
    PropertyOnboardingDocument,
    Payment,
    AccountingReceipt,
    ExpenseCategory,
    PropertyOwnerIntake,
    ExistingResidentIntake,
    LandlordIntake,
    AdverseActionNotice,
    RentalListing,
    RentalListingChannel,
    ReportTemplate,
)


class BlogCommentForm(forms.ModelForm):
    class Meta:
        model = BlogComment
        fields = ["name", "email", "comment"]
        widgets = {
            "name": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Your name",
            }),
            "email": forms.EmailInput(attrs={
                "class": "form-control",
                "placeholder": "Your email optional",
            }),
            "comment": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Write your comment...",
            }),
        }


class FinancialUploadForm(forms.ModelForm):
    class Meta:
        model = FinancialUpload
        fields = ["property", "ledger_scope", "name", "file", "notes"]
        labels = {
            "property": "Property",
            "ledger_scope": "Ledger",
            "name": "Import name",
            "file": "Accounting export or data file",
            "notes": "Source system / import notes",
        }
        help_texts = {
            "name": "Example: QuickBooks May 2026 P&L, AppFolio rent roll, Google Sheets export.",
            "file": "Upload CSV, XLSX, exported spreadsheet, ledger report, rent roll, or accounting-system export.",
            "notes": "Add the source system, property, date range, and anything needed to classify the data correctly.",
        }
        widgets = {
            "property": forms.Select(attrs={"class": "form-select"}),
            "ledger_scope": forms.Select(attrs={"class": "form-select"}),
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "file": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }

    def __init__(self, *args, properties=None, **kwargs):
        super().__init__(*args, **kwargs)
        if properties is not None:
            self.fields["property"].queryset = properties
        self.fields["property"].required = True


class CompanyEmailComposeForm(forms.Form):
    to_email = forms.EmailField(
        label="To",
        widget=forms.EmailInput(attrs={"class": "form-control", "placeholder": "recipient@example.com"}),
    )
    subject = forms.CharField(
        max_length=255,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    body = forms.CharField(
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 8}),
    )


class CompanyEmailReplyForm(forms.Form):
    body = forms.CharField(
        label="Reply",
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 7}),
    )


class AccountingReceiptForm(forms.ModelForm):
    new_category = forms.CharField(
        required=False,
        label="Add New Category",
        help_text="Use this when the right category is not in the list yet.",
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Example: Plumbing Repairs, Insurance, Power",
        }),
    )

    class Meta:
        model = AccountingReceipt
        fields = [
            "property",
            "receipt_file",
            "vendor",
            "receipt_date",
            "entry_type",
            "category",
            "new_category",
            "description",
            "amount",
            "payment_method",
            "notes",
        ]
        labels = {
            "receipt_file": "Receipt / Invoice File",
            "receipt_date": "Receipt Date",
            "entry_type": "Accounting Type",
            "amount": "Amount",
        }
        help_texts = {
            "receipt_file": "Upload the original receipt, invoice, or PDF. Rental Ledger Pro stores it as proof.",
            "amount": "Enter the amount if you know it. OCR may prefill this after upload when the file contains readable text.",
        }
        widgets = {
            "property": forms.Select(attrs={"class": "form-select"}),
            "receipt_file": forms.ClearableFileInput(attrs={"class": "form-control", "accept": "image/*,.pdf"}),
            "vendor": forms.TextInput(attrs={"class": "form-control", "placeholder": "Vendor / Payee"}),
            "receipt_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "entry_type": forms.Select(attrs={"class": "form-select"}),
            "category": forms.Select(attrs={"class": "form-select"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "payment_method": forms.Select(attrs={"class": "form-select"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }

    def __init__(self, *args, properties=None, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

        if properties is not None:
            self.fields["property"].queryset = properties

        self.fields["category"].queryset = ExpenseCategory.objects.filter(is_active=True).order_by("entry_type", "name")
        self.fields["category"].required = False
        self.fields["amount"].required = False

    def save(self, commit=True):
        receipt = super().save(commit=False)
        new_category = self.cleaned_data.get("new_category", "").strip()

        if new_category:
            category = ExpenseCategory.objects.filter(name__iexact=new_category).first()

            if not category:
                category = ExpenseCategory.objects.create(
                    name=new_category,
                    entry_type=receipt.entry_type,
                    created_by=self.user,
                )

            receipt.category = category

        if receipt.category and not receipt.entry_type:
            receipt.entry_type = receipt.category.entry_type

        if self.user and not receipt.uploaded_by:
            receipt.uploaded_by = self.user

        if commit:
            receipt.save()

        return receipt


class MultipleImageInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleImageField(forms.ImageField):
    def clean(self, data, initial=None):
        single_image_clean = super().clean

        if isinstance(data, (list, tuple)):
            return [single_image_clean(image, initial) for image in data]

        return [single_image_clean(data, initial)] if data else []


class MultipleFileField(forms.FileField):
    def clean(self, data, initial=None):
        single_file_clean = super().clean

        if isinstance(data, (list, tuple)):
            return [single_file_clean(file_obj, initial) for file_obj in data]

        return [single_file_clean(data, initial)] if data else []


class RentalListingPhotoInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class RentalListingPhotoField(forms.FileField):
    widget = RentalListingPhotoInput

    def clean(self, data, initial=None):
        single_file_clean = super().clean

        if isinstance(data, (list, tuple)):
            return [single_file_clean(file_obj, initial) for file_obj in data]

        return [single_file_clean(data, initial)] if data else []


class OwnerPropertyForm(forms.ModelForm):
    gallery_images = MultipleImageField(
        required=False,
        label="Gallery Pics",
        help_text="Add up to 9 property gallery pictures.",
        widget=MultipleImageInput(attrs={"class": "form-control", "accept": "image/*"}),
    )
    tenant_utility_vendors = forms.CharField(
        required=False,
        label="Tenant utility setup vendors",
        help_text="Optional. One per line: Service | Provider | setup link | phone | notes. Example: Power | Pacific Power | https://www.pacificpower.net | 888-221-7070",
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 5}),
    )

    class Meta:
        model = Property
        fields = [
            "name",
            "address",
            "description",
            "photo",
            "gallery_images",
            "unit_size",
            "available_date",
            "deposit_amount",
            "rent_amount",
            "lease_type",
            "move_in_cost_type",
            "move_in_cost_notes",
            "charges_application_fee",
            "application_fee_amount",
            "application_fee_notes",
            "requires_background_check",
            "background_check_fee_amount",
            "background_check_instructions",
            "screening_provider_name",
            "screening_provider_cost",
            "screening_admin_fee",
            "screening_criteria",
            "screening_fee_disclosure",
            "renters_insurance_provider_name",
            "renters_insurance_url",
            "renters_insurance_notes",
            "availability_status",
            "availability_message",
        ]
        labels = {
            "photo": "Cover Photo",
            "rent_amount": "Rent",
            "lease_type": "Rental Term",
            "move_in_cost_type": "Move-In Cost Requirement",
            "move_in_cost_notes": "Other Move-In Cost Description",
            "charges_application_fee": "Charge Application Fee",
            "application_fee_amount": "Application Fee Amount",
            "requires_background_check": "Require Background Check",
            "background_check_fee_amount": "Background Check Fee Amount",
            "screening_provider_name": "Screening Provider",
            "screening_provider_cost": "Screening Provider Cost",
            "screening_admin_fee": "Client Admin Fee",
            "screening_criteria": "Written Screening Criteria",
            "screening_fee_disclosure": "Applicant Fee / Screening Disclosure",
            "renters_insurance_provider_name": "Renters Insurance Provider",
            "renters_insurance_url": "Renters Insurance Link",
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "address": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
            "photo": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "unit_size": forms.TextInput(attrs={"class": "form-control"}),
            "available_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "deposit_amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "rent_amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "lease_type": forms.Select(attrs={"class": "form-select"}),
            "move_in_cost_type": forms.Select(attrs={"class": "form-select"}),
            "move_in_cost_notes": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Example: first month + $500 admin fee + deposit",
            }),
            "charges_application_fee": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "application_fee_amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "application_fee_notes": forms.TextInput(attrs={"class": "form-control"}),
            "requires_background_check": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "background_check_fee_amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "background_check_instructions": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "screening_provider_name": forms.TextInput(attrs={"class": "form-control"}),
            "screening_provider_cost": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "screening_admin_fee": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "screening_criteria": forms.Textarea(attrs={"class": "form-control", "rows": 5}),
            "screening_fee_disclosure": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
            "renters_insurance_provider_name": forms.TextInput(attrs={"class": "form-control"}),
            "renters_insurance_url": forms.URLInput(attrs={"class": "form-control"}),
            "renters_insurance_notes": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "availability_status": forms.Select(attrs={"class": "form-select"}),
            "availability_message": forms.TextInput(attrs={"class": "form-control"}),
        }

    def save_utility_vendors(self, property_obj):
        from .models import PropertyUtilityVendor

        raw_lines = self.cleaned_data.get("tenant_utility_vendors", "").splitlines()
        PropertyUtilityVendor.objects.filter(property=property_obj).delete()

        for index, raw_line in enumerate(raw_lines, start=1):
            parts = [part.strip() for part in raw_line.split("|")]
            parts += [""] * (5 - len(parts))
            service_type, provider_name, setup_url, phone, notes = parts[:5]

            if not service_type or not provider_name:
                continue

            if setup_url and not setup_url.lower().startswith(("http://", "https://")):
                setup_url = f"https://{setup_url}"

            PropertyUtilityVendor.objects.create(
                property=property_obj,
                service_type=service_type,
                provider_name=provider_name,
                setup_url=setup_url,
                phone=phone,
                notes=notes,
                sort_order=index,
            )

    def clean_gallery_images(self):
        gallery_images = self.cleaned_data.get("gallery_images", [])

        if len(gallery_images) > 9:
            raise forms.ValidationError("Upload no more than 9 gallery pictures.")

        return gallery_images


class OwnerFinancialUploadForm(FinancialUploadForm):
    property = forms.ModelChoiceField(queryset=Property.objects.none(), widget=forms.Select(attrs={"class": "form-select"}))

    class Meta(FinancialUploadForm.Meta):
        fields = ["property", "name", "file", "notes"]

    def __init__(self, *args, properties=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["property"].queryset = properties if properties is not None else Property.objects.none()


class RentalListingForm(forms.ModelForm):
    photos = RentalListingPhotoField(
        required=False,
        label="Unit and property photos",
        help_text="Upload interior unit layout photos first, then exterior/community photos.",
        widget=RentalListingPhotoInput(attrs={"class": "form-control", "accept": "image/*"}),
    )

    class Meta:
        model = RentalListing
        fields = [
            "property",
            "unit_label",
            "headline",
            "rent_amount",
            "deposit_amount",
            "utilities_description",
            "lease_terms",
            "available_date",
            "bedrooms",
            "bathrooms",
            "square_feet",
            "unit_layout_description",
            "property_benefits",
            "amenities",
            "screening_summary",
            "listing_body",
            "status",
        ]
        widgets = {
            "property": forms.Select(attrs={"class": "form-select"}),
            "unit_label": forms.TextInput(attrs={"class": "form-control", "placeholder": "Example: H, 204, Studio B"}),
            "headline": forms.TextInput(attrs={"class": "form-control", "maxlength": "180"}),
            "rent_amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "deposit_amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "utilities_description": forms.TextInput(attrs={"class": "form-control"}),
            "lease_terms": forms.TextInput(attrs={"class": "form-control"}),
            "available_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "bedrooms": forms.TextInput(attrs={"class": "form-control"}),
            "bathrooms": forms.TextInput(attrs={"class": "form-control"}),
            "square_feet": forms.NumberInput(attrs={"class": "form-control", "min": "0"}),
            "unit_layout_description": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
            "property_benefits": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
            "amenities": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
            "screening_summary": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "listing_body": forms.Textarea(attrs={"class": "form-control", "rows": 7}),
            "status": forms.Select(attrs={"class": "form-select"}),
        }
        labels = {
            "unit_label": "Unit / Room / Space",
            "rent_amount": "Monthly Rent",
            "deposit_amount": "Deposit",
            "listing_body": "Public Listing Description",
        }

    def __init__(self, *args, properties=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["property"].queryset = properties if properties is not None else Property.objects.none()


class RentalListingChannelForm(forms.ModelForm):
    class Meta:
        model = RentalListingChannel
        fields = ["status", "external_url", "notes"]
        widgets = {
            "status": forms.Select(attrs={"class": "form-select form-select-sm"}),
            "external_url": forms.URLInput(attrs={"class": "form-control form-control-sm"}),
            "notes": forms.Textarea(attrs={"class": "form-control form-control-sm", "rows": 2}),
        }


class OwnerPropertyOnboardingDocumentsForm(forms.Form):
    application_file = forms.FileField(
        required=False,
        label="Property rental application",
        widget=forms.ClearableFileInput(attrs={"class": "form-control"}),
    )
    lease_file = forms.FileField(
        required=False,
        label="Property lease agreement",
        widget=forms.ClearableFileInput(attrs={"class": "form-control"}),
    )
    other_documents = MultipleFileField(
        required=False,
        label="Other onboarding documents",
        widget=MultipleFileInput(attrs={"class": "form-control"}),
    )

    def save(self, property_obj):
        application_file = self.cleaned_data.get("application_file")
        lease_file = self.cleaned_data.get("lease_file")

        if application_file:
            PropertyOnboardingDocument.objects.create(
                property=property_obj,
                document_type="application",
                title=application_file.name,
                source_file=application_file,
            )

        if lease_file:
            PropertyOnboardingDocument.objects.create(
                property=property_obj,
                document_type="lease",
                title=lease_file.name,
                source_file=lease_file,
            )

        for onboarding_file in self.cleaned_data.get("other_documents", []):
            PropertyOnboardingDocument.objects.create(
                property=property_obj,
                document_type="other",
                title=onboarding_file.name,
                source_file=onboarding_file,
            )


class OwnerLandlordInviteForm(forms.ModelForm):
    property = forms.ModelChoiceField(queryset=Property.objects.none(), widget=forms.Select(attrs={"class": "form-select"}))

    class Meta:
        model = LandlordIntake
        fields = ["property", "full_name", "email", "phone", "address"]
        labels = {
            "property": "Property this landlord will manage",
            "full_name": "Landlord name",
            "email": "Landlord email",
            "phone": "Landlord phone",
            "address": "Landlord address",
        }
        widgets = {
            "full_name": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "phone": forms.TextInput(attrs={"class": "form-control"}),
            "address": forms.TextInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, properties=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["property"].queryset = properties if properties is not None else Property.objects.none()


class PropertyOwnerIntakeForm(forms.ModelForm):
    REPORT_CHOICES = [
        ("t12", "T-12 / NOI report"),
        ("rent_roll", "Rent roll"),
        ("delinquency_report", "Delinquency report"),
        ("deposit_liability", "Deposit liability report"),
        ("income_statement", "Income statement / P&L"),
        ("expense_by_category", "Expense detail by category"),
        ("vendor_expense", "Vendor expense report"),
        ("property_performance_summary", "Property performance summary"),
        ("valuation_estimate", "Valuation estimate report"),
        ("insurance_compliance", "Insurance / compliance report"),
        ("capital_improvement_log", "Capital improvement log"),
        ("utility_cost_trend", "Utility usage/cost trend"),
    ]

    property_types = forms.MultipleChoiceField(
        choices=PropertyOwnerIntake.PROPERTY_TYPE_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Property types",
    )
    desired_reports = forms.MultipleChoiceField(
        choices=REPORT_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Reports you want available",
    )

    class Meta:
        model = PropertyOwnerIntake
        fields = [
            "full_name",
            "company_name",
            "email",
            "phone",
            "property_count",
            "total_units",
            "property_types",
            "current_software",
            "current_pain_points",
            "migration_notes",
            "needs_rent_collection",
            "needs_accounting",
            "needs_owner_reporting",
            "needs_data_migration",
            "needs_resident_files",
            "needs_documents",
            "needs_maintenance",
            "needs_resident_communication",
            "needs_screening",
            "needs_property_websites",
            "charges_application_fee",
            "performs_background_checks",
            "advertises_available_units",
            "uses_automatic_late_fees",
            "needs_custom_reports",
            "desired_reports",
            "offers_renters_insurance",
            "tenant_utility_setup_notes",
            "onboarding_timeline",
            "dashboard_goals",
            "additional_notes",
        ]
        labels = {
            "property_count": "How many properties do you manage or own?",
            "total_units": "Approximate total units",
            "current_software": "Current software or accounting system",
            "current_pain_points": "What is hardest in your current process?",
            "migration_notes": "Data that must be migrated or preserved",
            "needs_rent_collection": "Online rent and fee collection",
            "needs_accounting": "Accounting, ledgers, and commercial property reports",
            "needs_owner_reporting": "Owner statements, NOI, T-12, and rent roll reporting",
            "needs_data_migration": "Migration from current software or spreadsheets",
            "needs_resident_files": "Resident files, balances, and payment records",
            "needs_documents": "Leases, signatures, document storage, and forms",
            "needs_maintenance": "Maintenance requests and work tracking",
            "needs_resident_communication": "Resident messaging and property announcements",
            "needs_screening": "Rental applications, scoring support, and screening workflow",
            "needs_property_websites": "Property pages, availability, and application intake",
            "charges_application_fee": "Charges application fees",
            "performs_background_checks": "Uses background checks",
            "advertises_available_units": "Advertises available units",
            "uses_automatic_late_fees": "Automatically charges late fees",
            "needs_custom_reports": "Needs custom reports",
            "desired_reports": "Reports you want available",
            "offers_renters_insurance": "Offers or requires renters insurance",
            "tenant_utility_setup_notes": "Utility accounts tenants must set up",
            "onboarding_timeline": "When do you need to start?",
            "dashboard_goals": "What should your dashboard make easy?",
        }
        widgets = {
            "full_name": forms.TextInput(attrs={"class": "form-control"}),
            "company_name": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "phone": forms.TextInput(attrs={"class": "form-control"}),
            "property_count": forms.NumberInput(attrs={"class": "form-control", "min": "1"}),
            "total_units": forms.NumberInput(attrs={"class": "form-control", "min": "0"}),
            "current_software": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "QuickBooks, AppFolio, Buildium, spreadsheets, none, etc.",
            }),
            "current_pain_points": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "migration_notes": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "onboarding_timeline": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Example: this month, next quarter, evaluating options",
            }),
            "dashboard_goals": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
            "tenant_utility_setup_notes": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 4,
                "placeholder": "Example: Power | Pacific Power | https://www.pacificpower.net | 888-221-7070",
            }),
            "additional_notes": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }

    def clean_desired_reports(self):
        return ", ".join(self.cleaned_data.get("desired_reports") or [])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance and self.instance.pk and self.instance.property_types:
            self.initial["property_types"] = self.instance.property_types.split(",")

        feature_fields = [
            "needs_rent_collection",
            "needs_accounting",
            "needs_owner_reporting",
            "needs_data_migration",
            "needs_resident_files",
            "needs_documents",
            "needs_maintenance",
            "needs_resident_communication",
            "needs_screening",
            "needs_property_websites",
            "charges_application_fee",
            "performs_background_checks",
            "advertises_available_units",
            "uses_automatic_late_fees",
            "needs_custom_reports",
            "offers_renters_insurance",
        ]

        for field_name in feature_fields:
            self.fields[field_name].widget.attrs["class"] = "form-check-input"

    def save(self, commit=True):
        intake = super().save(commit=False)
        intake.property_types = ",".join(self.cleaned_data.get("property_types", []))

        if commit:
            intake.save()

        return intake


class PropertyOwnerLeadPipelineForm(forms.ModelForm):
    class Meta:
        model = PropertyOwnerIntake
        fields = ["lead_stage", "follow_up_date", "internal_notes"]
        labels = {
            "lead_stage": "Lead stage",
            "follow_up_date": "Follow-up date",
            "internal_notes": "Internal notes",
        }
        widgets = {
            "lead_stage": forms.Select(attrs={"class": "form-select"}),
            "follow_up_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "internal_notes": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 5,
                "placeholder": "Call notes, demo needs, pricing questions, next step, objections, or onboarding plan.",
            }),
        }


class ExistingResidentIntakeForm(forms.ModelForm):
    class Meta:
        model = ExistingResidentIntake
        fields = [
            "first_name",
            "middle_name",
            "last_name",
            "email",
            "phone",
            "room_unit_label",
            "profile_photo",
            "sms_opted_in",
            "has_valid_odl",
            "years_at_residence",
            "move_in_month",
            "additional_notes",
        ]
        labels = {
            "middle_name": "Middle name",
            "room_unit_label": "Current Room / Unit # / Label",
            "profile_photo": "Selfie or profile photo",
            "sms_opted_in": "Yes, I agree to receive text messages from Bowling Legacy",
            "has_valid_odl": "I have a valid Oregon driver's license",
            "years_at_residence": "Years at this residence",
            "move_in_month": "Month you moved in",
            "additional_notes": "Anything we should know for your profile",
        }
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "form-control"}),
            "middle_name": forms.TextInput(attrs={"class": "form-control"}),
            "last_name": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "phone": forms.TextInput(attrs={"class": "form-control"}),
            "room_unit_label": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Example: Room B, Unit 3, 204",
            }),
            "profile_photo": forms.ClearableFileInput(attrs={
                "class": "form-control",
                "accept": "image/*",
                "capture": "user",
            }),
            "sms_opted_in": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "has_valid_odl": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "years_at_residence": forms.NumberInput(attrs={"class": "form-control", "min": "0"}),
            "move_in_month": forms.TextInput(attrs={"class": "form-control", "type": "month"}),
            "additional_notes": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }


class CurrentResidentRosterUploadForm(forms.Form):
    property = forms.ModelChoiceField(
        queryset=Property.objects.none(),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    file = forms.FileField(
        label="Current resident list",
        help_text="CSV or Excel accepted. Include tenant/name, unit, phone, rent, due day, utilities, deposit held, last month paid, and balances when available.",
        widget=forms.ClearableFileInput(attrs={"class": "form-control", "accept": ".csv,.xlsx,.xls"}),
    )

    def __init__(self, *args, properties=None, **kwargs):
        super().__init__(*args, **kwargs)
        if properties is not None:
            self.fields["property"].queryset = properties


class ResidentRoomTransferForm(forms.Form):
    space_type = forms.CharField(
        label="Space Type",
        initial="Room",
        max_length=50,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    space_label = forms.CharField(
        label="New Room / Unit",
        max_length=50,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Example: L"}),
    )
    apply_room_rent = forms.BooleanField(
        label="Apply rent, utilities, and deposit settings from this room if they exist",
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )
    notes = forms.CharField(
        label="Transfer Notes",
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
    )


class GroupResidentMessageForm(forms.Form):
    DELIVERY_CHOICES = [
        ("portal", "Secure portal only"),
        ("portal_sms", "Secure portal + SMS text"),
    ]

    property_id = forms.ChoiceField(
        label="Send To",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    delivery_method = forms.ChoiceField(
        choices=DELIVERY_CHOICES,
        initial="portal",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    subject = forms.CharField(
        max_length=255,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Example: Water shutoff notice, rent reminder, building update",
        }),
    )
    message = forms.CharField(
        widget=forms.Textarea(attrs={
            "class": "form-control",
            "rows": 6,
            "placeholder": "Write the message residents will see in their secure portal...",
        }),
    )

    def __init__(self, *args, properties=None, **kwargs):
        super().__init__(*args, **kwargs)
        property_choices = [("all", "All accessible properties")]
        if properties is not None:
            property_choices.extend((str(property_obj.id), property_obj.name) for property_obj in properties)
        self.fields["property_id"].choices = property_choices


class ManualPaymentForm(forms.ModelForm):
    service_month = forms.DateField(
        label="Applies To Month",
        required=False,
        input_formats=["%Y-%m", "%Y-%m-%d"],
        widget=forms.DateInput(attrs={"class": "form-control", "type": "month"}),
        help_text="Use this when June rent is paid in May, or when a payment is for a future month.",
    )

    class Meta:
        model = Payment
        fields = [
            "application",
            "payment_type",
            "payment_method",
            "amount",
            "received_at",
            "service_month",
            "months_covered",
            "reference_number",
            "description",
            "notes",
        ]
        widgets = {
            "application": forms.Select(attrs={"class": "form-select"}),
            "payment_type": forms.Select(attrs={"class": "form-select"}),
            "payment_method": forms.Select(attrs={"class": "form-select"}),
            "amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0.01"}),
            "received_at": forms.DateTimeInput(attrs={"class": "form-control", "type": "datetime-local"}),
            "months_covered": forms.NumberInput(attrs={"class": "form-control", "min": "1", "max": "24"}),
            "reference_number": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Bank confirmation, Cash App note, check number, etc.",
            }),
            "description": forms.TextInput(attrs={"class": "form-control"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["payment_type"].choices = [("", "Choose what this payment applies to")] + list(Payment.PAYMENT_TYPE_CHOICES)
        self.fields["payment_type"].required = True
        self.fields["months_covered"].required = False
        self.fields["months_covered"].help_text = "Use 1 for a normal monthly payment. Use 2 or more when one payment covers multiple months."
        self.fields["application"].queryset = (
            HousingApplication.objects
            .select_related("property")
            .order_by("property__name", "space_label", "full_name")
        )

    def clean_months_covered(self):
        months_covered = self.cleaned_data.get("months_covered") or 1
        return min(max(months_covered, 1), 24)

    def clean_service_month(self):
        service_month = self.cleaned_data.get("service_month")
        if service_month:
            return service_month.replace(day=1)
        return service_month


class ResidentBalanceCorrectionForm(forms.ModelForm):
    class Meta:
        model = HousingApplication
        fields = [
            "monthly_rent",
            "balance",
            "utility_monthly",
            "utility_balance",
            "deposit_required",
            "deposit_paid",
            "rent_due_day",
        ]
        labels = {
            "balance": "Rent Balance Due",
            "utility_balance": "Utility Balance Due",
        }
        widgets = {
            "monthly_rent": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "balance": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "utility_monthly": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "utility_balance": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "deposit_required": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "deposit_paid": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "rent_due_day": forms.NumberInput(attrs={"class": "form-control", "min": "1", "max": "31"}),
        }

    def clean(self):
        cleaned_data = super().clean()
        deposit_required = cleaned_data.get("deposit_required")
        deposit_paid = cleaned_data.get("deposit_paid")

        if deposit_required is not None and deposit_paid is not None and deposit_paid > deposit_required:
            self.add_error("deposit_paid", "Deposit paid cannot be greater than deposit required.")

        return cleaned_data


class CustomReportForm(forms.Form):
    REPORT_TYPE_CHOICES = [
        ("resident_phone_list", "Resident Phone List"),
        ("resident_roster", "Resident Roster"),
        ("resident_directory", "Resident Directory / Roster Export"),
        ("unit_rent_setup", "Unit Rent Setup"),
        ("delinquency_report", "Delinquency Report"),
        ("deposit_liability", "Deposit Liability Report"),
        ("payment_summary", "Payment Summary"),
        ("property_performance_summary", "Property Performance Summary"),
        ("valuation_estimate", "Valuation Estimate"),
        ("income_statement", "Income Statement / P&L"),
        ("expense_by_category", "Expense Detail by Category"),
        ("vendor_expense", "Vendor Expense Report"),
        ("occupancy_vacancy", "Occupancy / Vacancy Report"),
        ("capital_improvement_log", "Capital Improvement Log"),
        ("utility_cost_trend", "Utility Usage / Cost Trend"),
        ("insurance_compliance", "Insurance / Compliance Report"),
        ("financial_entries", "Financial Entries / Expenses"),
        ("receipt_expense_detail", "Receipt Expense Detail"),
        ("vendor_directory", "Vendor Directory"),
        ("vendor_category_summary", "Vendor / Category Summary"),
        ("data_inventory", "Property Data Inventory"),
    ]

    FINANCIAL_ENTRY_CHOICES = [
        ("income", "Income"),
        ("operating_expense", "Operating Expenses"),
        ("debt_service", "Debt Service"),
        ("capital_expense", "Capital Expenses"),
        ("other", "Other"),
    ]
    MATH_MODE_CHOICES = ReportTemplate.MATH_MODE_CHOICES

    report_type = forms.ChoiceField(
        choices=REPORT_TYPE_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    property_id = forms.ChoiceField(
        label="Property",
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    start_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
    )
    end_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
    )
    financial_entry_types = forms.MultipleChoiceField(
        choices=FINANCIAL_ENTRY_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
    )
    save_template = forms.BooleanField(
        label="Save this report setup",
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )
    template_name = forms.CharField(
        label="Template name",
        required=False,
        max_length=120,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Monthly utility cost report"}),
    )
    math_mode = forms.ChoiceField(
        label="Extra math",
        choices=MATH_MODE_CHOICES,
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    math_column = forms.CharField(
        label="Column to calculate",
        required=False,
        max_length=120,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Amount, Rent, Utilities, Total"}),
    )

    def __init__(self, *args, properties=None, **kwargs):
        super().__init__(*args, **kwargs)
        property_choices = [("", "All accessible properties")]

        if properties is not None:
            property_choices.extend((str(property_obj.id), property_obj.name) for property_obj in properties)

        self.fields["property_id"].choices = property_choices

    def clean(self):
        cleaned_data = super().clean()
        save_template = cleaned_data.get("save_template")
        template_name = (cleaned_data.get("template_name") or "").strip()
        math_mode = cleaned_data.get("math_mode")
        math_column = (cleaned_data.get("math_column") or "").strip()

        if save_template and not template_name:
            self.add_error("template_name", "Enter a name before saving this report template.")

        if math_mode in ["sum", "average"] and not math_column:
            self.add_error("math_column", "Enter the column name to calculate.")

        return cleaned_data


class ResidentMoveOutForm(forms.Form):
    move_out_date = forms.DateField(
        label="Move-out date",
        required=True,
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
    )
    archive_notes = forms.CharField(
        label="Archive notes",
        required=False,
        widget=forms.Textarea(attrs={
            "class": "form-control",
            "rows": 3,
            "placeholder": "Optional notes about keys, deposit, cleaning, forwarding address, or final balance.",
        }),
    )


class LandlordCreateTenantForm(forms.Form):
    lease_start_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            "class": "form-control",
            "type": "date",
        }),
    )

    monthly_rent = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        initial=0,
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "step": "0.01",
        }),
    )

    balance = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        initial=0,
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "step": "0.01",
        }),
    )

    rent_due_day = forms.IntegerField(
        initial=1,
        min_value=1,
        max_value=31,
        widget=forms.NumberInput(attrs={
            "class": "form-control",
        }),
    )

    lease_end_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            "class": "form-control",
            "type": "date",
        }),
    )

    deposit_required = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        initial=450,
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "step": "0.01",
        }),
    )

    deposit_paid = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        initial=0,
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "step": "0.01",
        }),
    )

    deposit_payment_plan = forms.ChoiceField(
        choices=HousingApplication.DEPOSIT_PAYMENT_PLAN_CHOICES,
        initial="paid_in_full",
        widget=forms.Select(attrs={
            "class": "form-select",
        }),
        help_text="If the 90-day plan is selected, the lease will include a deposit payment amendment.",
    )

    utility_monthly = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        initial=66,
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "step": "0.01",
        }),
    )

    utility_balance = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        initial=0,
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "step": "0.01",
        }),
    )

    space_type = forms.CharField(
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Room, Unit, Space, Suite",
        }),
    )

    space_label = forms.CharField(
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Example: A, 101, Suite 2",
        }),
    )

    additional_notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            "class": "form-control",
            "rows": 3,
            "placeholder": "Landlord notes",
        }),
    )


class ResidentDocumentUploadForm(forms.ModelForm):
    class Meta:
        model = ApplicantDocument
        fields = ["document_type", "name", "file"]
        widgets = {
            "document_type": forms.Select(attrs={"class": "form-select"}),
            "name": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Example: May pay stub, Social Security award letter, bank statement",
            }),
            "file": forms.ClearableFileInput(attrs={"class": "form-control"}),
        }


class TenantFilePacketUploadForm(forms.Form):
    TARGET_CHOICES = [
        ("resident", "Existing resident file"),
        ("archived", "Archived resident file"),
        ("unit", "Empty unit / no tenant yet"),
    ]

    target_type = forms.ChoiceField(
        choices=TARGET_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    property = forms.ModelChoiceField(
        queryset=Property.objects.none(),
        required=True,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    application = forms.ModelChoiceField(
        label="Resident file",
        queryset=HousingApplication.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    unit_label = forms.CharField(
        label="Unit / room",
        required=False,
        max_length=50,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Example: B, 204, Suite 3"}),
    )
    document_type = forms.ChoiceField(
        choices=ApplicantDocument.DOCUMENT_TYPE_CHOICES,
        initial="other",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    name = forms.CharField(
        max_length=255,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Example: Signed lease packet, scanned tenant file"}),
    )
    file = forms.FileField(widget=forms.ClearableFileInput(attrs={"class": "form-control"}))
    packet_notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Optional notes about what this packet contains."}),
    )
    run_ocr = forms.BooleanField(
        label="Try to read scanned text now",
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    def __init__(self, *args, properties=None, applications=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["property"].queryset = properties or Property.objects.none()
        self.fields["application"].queryset = applications or HousingApplication.objects.none()

    def clean(self):
        cleaned_data = super().clean()
        target_type = cleaned_data.get("target_type")
        application = cleaned_data.get("application")
        unit_label = (cleaned_data.get("unit_label") or "").strip()

        if target_type in ["resident", "archived"] and not application:
            self.add_error("application", "Choose the resident file this packet belongs to.")

        if target_type == "unit" and not unit_label:
            self.add_error("unit_label", "Enter the unit or room label for this packet.")

        return cleaned_data


class TenantFilePacketReassignForm(forms.Form):
    application = forms.ModelChoiceField(
        label="Move packet to resident file",
        queryset=HousingApplication.objects.none(),
        required=True,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def __init__(self, *args, applications=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["application"].queryset = applications or HousingApplication.objects.none()


class ResidentProfilePhotoForm(forms.ModelForm):
    class Meta:
        model = HousingApplication
        fields = ["profile_photo"]
        labels = {
            "profile_photo": "Profile photo",
        }
        widgets = {
            "profile_photo": forms.FileInput(attrs={
                "class": "visually-hidden",
                "accept": "image/*",
            }),
        }


class ResidentMessageForm(forms.ModelForm):
    class Meta:
        model = ResidentMessage
        fields = ["message_type", "subject", "message"]
        widgets = {
            "message_type": forms.Select(attrs={"class": "form-select"}),
            "subject": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Subject",
            }),
            "message": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 5,
                "placeholder": "Write your request or message here...",
            }),
        }


class HousingApplicationForm(forms.ModelForm):
    class Meta:
        model = HousingApplication
        fields = [
            "full_name",
            "phone",
            "email",
            "age",
            "sms_opted_in",
            "screening_consent",
            "current_address",
            "current_address_length",
            "previous_address_1",
            "previous_address_1_length",
            "previous_address_2",
            "previous_address_2_length",
            "previous_address_3",
            "previous_address_3_length",
            "drivers_license_number",
            "has_valid_odl",
            "oregon_id_number",
            "id_upload",
            "income_source",
            "monthly_income",
            "employer_name",
            "employment_length",
            "previous_evictions",
            "in_recovery",
            "drug_of_choice",
            "on_parole",
            "parole_officer_name",
            "parole_officer_phone",
            "felony_history",
            "odoc_time_served",
            "reference_1_name",
            "reference_1_phone",
            "reference_1_relationship",
            "reference_1_type",
            "reference_2_name",
            "reference_2_phone",
            "reference_2_relationship",
            "reference_2_type",
            "housing_need",
            "additional_notes",
            "sobriety_acknowledgment",
            "unconditional_regard_acknowledgment",
        ]

        widgets = {
            "full_name": forms.TextInput(attrs={"class": "form-control"}),
            "phone": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "age": forms.NumberInput(attrs={"class": "form-control"}),
            "sms_opted_in": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "screening_consent": forms.CheckboxInput(attrs={"class": "form-check-input"}),

            "current_address": forms.TextInput(attrs={"class": "form-control"}),
            "current_address_length": forms.TextInput(attrs={"class": "form-control"}),
            "previous_address_1": forms.TextInput(attrs={"class": "form-control"}),
            "previous_address_1_length": forms.TextInput(attrs={"class": "form-control"}),
            "previous_address_2": forms.TextInput(attrs={"class": "form-control"}),
            "previous_address_2_length": forms.TextInput(attrs={"class": "form-control"}),
            "previous_address_3": forms.TextInput(attrs={"class": "form-control"}),
            "previous_address_3_length": forms.TextInput(attrs={"class": "form-control"}),

            "drivers_license_number": forms.TextInput(attrs={"class": "form-control"}),
            "has_valid_odl": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "oregon_id_number": forms.TextInput(attrs={"class": "form-control"}),
            "id_upload": forms.ClearableFileInput(attrs={"class": "form-control"}),

            "income_source": forms.TextInput(attrs={"class": "form-control"}),
            "monthly_income": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "employer_name": forms.TextInput(attrs={"class": "form-control"}),
            "employment_length": forms.TextInput(attrs={"class": "form-control"}),

            "previous_evictions": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "in_recovery": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "drug_of_choice": forms.TextInput(attrs={"class": "form-control"}),
            "on_parole": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "parole_officer_name": forms.TextInput(attrs={"class": "form-control"}),
            "parole_officer_phone": forms.TextInput(attrs={"class": "form-control"}),
            "felony_history": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "odoc_time_served": forms.CheckboxInput(attrs={"class": "form-check-input"}),

            "reference_1_name": forms.TextInput(attrs={"class": "form-control"}),
            "reference_1_phone": forms.TextInput(attrs={"class": "form-control"}),
            "reference_1_relationship": forms.TextInput(attrs={"class": "form-control"}),
            "reference_1_type": forms.TextInput(attrs={"class": "form-control"}),

            "reference_2_name": forms.TextInput(attrs={"class": "form-control"}),
            "reference_2_phone": forms.TextInput(attrs={"class": "form-control"}),
            "reference_2_relationship": forms.TextInput(attrs={"class": "form-control"}),
            "reference_2_type": forms.TextInput(attrs={"class": "form-control"}),

            "housing_need": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
            "additional_notes": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "sobriety_acknowledgment": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "unconditional_regard_acknowledgment": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
        labels = {
            "sms_opted_in": "Yes, I agree to receive text messages from Bowling Legacy",
            "screening_consent": "I consent to applicant screening and background-check processing for this property",
        }
        help_texts = {
            "sms_opted_in": "Message frequency varies. Message and data rates may apply. Reply STOP to opt out or HELP for help. Consent is not required to rent from Bowling Legacy.",
            "screening_consent": "Consent allows the property owner or landlord to order and review applicant screening reports when required. Rental Ledger Pro stores the report workflow for the owner but does not make the final rental decision.",
        }


class ScreeningReviewForm(forms.ModelForm):
    class Meta:
        model = HousingApplication
        fields = [
            "background_check_status",
            "background_report",
            "screening_score",
            "screening_rating",
            "screening_review_summary",
            "owner_final_decision",
            "owner_decision_notes",
        ]
        widgets = {
            "background_check_status": forms.Select(attrs={"class": "form-select"}),
            "background_report": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "screening_score": forms.NumberInput(attrs={"class": "form-control", "min": "0", "max": "100"}),
            "screening_rating": forms.Select(attrs={"class": "form-select"}),
            "screening_review_summary": forms.Textarea(attrs={"class": "form-control", "rows": 6}),
            "owner_final_decision": forms.Select(attrs={"class": "form-select"}),
            "owner_decision_notes": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
        }
        labels = {
            "background_check_status": "Background Report Status",
            "background_report": "Upload Background / Screening Report",
            "screening_score": "Suggested Score",
            "screening_rating": "Suggested Rating",
            "screening_review_summary": "Screening Review Summary",
            "owner_final_decision": "Owner / Landlord Decision",
            "owner_decision_notes": "Owner / Landlord Decision Notes",
        }


class AdverseActionNoticeForm(forms.ModelForm):
    class Meta:
        model = AdverseActionNotice
        fields = [
            "action_type",
            "reasons",
            "screening_company_name",
            "screening_company_contact",
            "owner_landlord_name",
            "owner_landlord_contact",
            "notice_body",
        ]
        widgets = {
            "action_type": forms.Select(attrs={"class": "form-select"}),
            "reasons": forms.Textarea(attrs={"class": "form-control", "rows": 5}),
            "screening_company_name": forms.TextInput(attrs={"class": "form-control"}),
            "screening_company_contact": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "owner_landlord_name": forms.TextInput(attrs={"class": "form-control"}),
            "owner_landlord_contact": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "notice_body": forms.Textarea(attrs={"class": "form-control", "rows": 8}),
        }


class InviteCodeForm(forms.Form):
    invite_code = forms.CharField(
        max_length=6,
        label="Enter your invite code",
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Enter invite code",
        }),
    )


class ReplacementInviteCodeForm(forms.Form):
    email = forms.EmailField(
        label="Email on your approved application or questionnaire",
        widget=forms.EmailInput(attrs={
            "class": "form-control",
            "placeholder": "Enter the email you submitted",
        }),
    )


class SignUpForm(UserCreationForm):
    class Meta:
        model = User
        fields = ["username", "email", "password1", "password2"]
        widgets = {
            "username": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
        }


class LandlordSignUpForm(SignUpForm):
    full_name = forms.CharField(
        max_length=255,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    phone = forms.CharField(
        max_length=50,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    address = forms.CharField(
        max_length=255,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
