from decimal import Decimal

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


DEFAULT_PLATFORM_FEES = [
    {
        "name": "Starter property subscription",
        "category": "subscription",
        "billing_type": "monthly",
        "default_amount": Decimal("19.00"),
        "percentage_rate": Decimal("0.000"),
        "public_label": "Starter property subscription",
        "description": "Monthly software subscription for small properties that need reports, ledgers, resident files, and payment tracking.",
    },
    {
        "name": "Portfolio property subscription",
        "category": "subscription",
        "billing_type": "monthly",
        "default_amount": Decimal("39.00"),
        "percentage_rate": Decimal("0.000"),
        "public_label": "Portfolio property subscription",
        "description": "Monthly software subscription for larger or multi-property portfolios.",
    },
    {
        "name": "Stripe platform margin",
        "category": "stripe_platform_fee",
        "billing_type": "per_payment",
        "default_amount": Decimal("0.00"),
        "percentage_rate": Decimal("0.500"),
        "public_label": "Online payment platform fee",
        "description": "Optional Rental Ledger Pro margin on processed payments, tracked separately from owner rent income.",
    },
    {
        "name": "Application processing admin fee",
        "category": "application_processing",
        "billing_type": "per_application",
        "default_amount": Decimal("5.00"),
        "percentage_rate": Decimal("0.000"),
        "public_label": "Application processing",
        "description": "Platform-side admin fee charged to the client or included in the owner's applicant fee policy.",
    },
    {
        "name": "Background screening admin fee",
        "category": "background_screening_admin",
        "billing_type": "per_screening",
        "default_amount": Decimal("7.00"),
        "percentage_rate": Decimal("0.000"),
        "public_label": "Background screening handling",
        "description": "Administrative margin for ordering, tracking, and routing background screening reports.",
    },
    {
        "name": "Data migration setup",
        "category": "migration_setup",
        "billing_type": "one_time",
        "default_amount": Decimal("149.00"),
        "percentage_rate": Decimal("0.000"),
        "public_label": "Data migration setup",
        "description": "One-time fee for converting owner spreadsheets, rent rolls, resident files, and accounting exports.",
    },
    {
        "name": "Premium valuation report",
        "category": "premium_report",
        "billing_type": "per_report",
        "default_amount": Decimal("49.00"),
        "percentage_rate": Decimal("0.000"),
        "public_label": "Premium property valuation report",
        "description": "Optional enhanced valuation, NOI, cap-rate, and lender-ready reporting package.",
    },
    {
        "name": "Vacancy listing push",
        "category": "vacancy_listing",
        "billing_type": "per_listing",
        "default_amount": Decimal("15.00"),
        "percentage_rate": Decimal("0.000"),
        "public_label": "Vacancy listing service",
        "description": "Fee for preparing and distributing rental vacancy listings to supported channels.",
    },
    {
        "name": "Renters insurance referral",
        "category": "insurance_referral",
        "billing_type": "referral",
        "default_amount": Decimal("0.00"),
        "percentage_rate": Decimal("0.000"),
        "public_label": "Renters insurance referral",
        "description": "Referral or advertising revenue from renters insurance placement.",
    },
    {
        "name": "Vendor referral",
        "category": "vendor_referral",
        "billing_type": "referral",
        "default_amount": Decimal("0.00"),
        "percentage_rate": Decimal("0.000"),
        "public_label": "Vendor referral",
        "description": "Revenue from verified vendor, service provider, or partner referrals.",
    },
]


def seed_platform_fee_settings(apps, schema_editor):
    PlatformFeeSetting = apps.get_model("main", "PlatformFeeSetting")
    for fee in DEFAULT_PLATFORM_FEES:
        PlatformFeeSetting.objects.get_or_create(
            name=fee["name"],
            defaults=fee,
        )


def remove_seeded_platform_fee_settings(apps, schema_editor):
    PlatformFeeSetting = apps.get_model("main", "PlatformFeeSetting")
    PlatformFeeSetting.objects.filter(name__in=[fee["name"] for fee in DEFAULT_PLATFORM_FEES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0050_stripe_payment_configuration"),
    ]

    operations = [
        migrations.CreateModel(
            name="PlatformFeeSetting",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=160)),
                ("category", models.CharField(choices=[("subscription", "Monthly subscription"), ("stripe_platform_fee", "Stripe platform fee"), ("application_processing", "Application processing"), ("background_screening_admin", "Background screening admin"), ("migration_setup", "Migration / setup"), ("premium_report", "Premium report"), ("vacancy_listing", "Vacancy listing"), ("insurance_referral", "Insurance referral"), ("vendor_referral", "Vendor referral"), ("advertising", "Advertising"), ("other", "Other")], max_length=40)),
                ("billing_type", models.CharField(choices=[("monthly", "Monthly"), ("per_payment", "Per payment"), ("per_application", "Per application"), ("per_screening", "Per screening"), ("one_time", "One time"), ("per_report", "Per report"), ("per_listing", "Per listing"), ("referral", "Referral"), ("advertising", "Advertising"), ("other", "Other")], max_length=30)),
                ("default_amount", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=10)),
                ("percentage_rate", models.DecimalField(decimal_places=3, default=Decimal("0.000"), help_text="Optional percentage, such as 1.000 for 1%.", max_digits=6)),
                ("public_label", models.CharField(blank=True, max_length=180)),
                ("description", models.TextField(blank=True)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["category", "name"],
            },
        ),
        migrations.CreateModel(
            name="PlatformRevenueEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("category", models.CharField(choices=[("subscription", "Monthly subscription"), ("stripe_platform_fee", "Stripe platform fee"), ("application_processing", "Application processing"), ("background_screening_admin", "Background screening admin"), ("migration_setup", "Migration / setup"), ("premium_report", "Premium report"), ("vacancy_listing", "Vacancy listing"), ("insurance_referral", "Insurance referral"), ("vendor_referral", "Vendor referral"), ("advertising", "Advertising"), ("other", "Other")], max_length=40)),
                ("source_owner_email", models.EmailField(blank=True, max_length=254)),
                ("description", models.CharField(max_length=255)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=10)),
                ("revenue_date", models.DateField(default=django.utils.timezone.localdate)),
                ("status", models.CharField(choices=[("expected", "Expected"), ("invoiced", "Invoiced"), ("received", "Received"), ("waived", "Waived"), ("cancelled", "Cancelled")], default="expected", max_length=20)),
                ("reference_number", models.CharField(blank=True, max_length=120)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_platform_revenue_entries", to=settings.AUTH_USER_MODEL)),
                ("fee_setting", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="revenue_entries", to="main.platformfeesetting")),
                ("source_payment", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="platform_revenue_entries", to="main.payment")),
                ("source_property", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="platform_revenue_entries", to="main.property")),
            ],
            options={
                "verbose_name_plural": "Platform revenue entries",
                "ordering": ["-revenue_date", "-created_at"],
            },
        ),
        migrations.RunPython(seed_platform_fee_settings, remove_seeded_platform_fee_settings),
    ]
