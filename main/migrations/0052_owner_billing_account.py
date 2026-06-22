from decimal import Decimal
from datetime import timedelta

from django.db import migrations, models
import django.utils.timezone


def seed_owner_billing_accounts(apps, schema_editor):
    Property = apps.get_model("main", "Property")
    OwnerBillingAccount = apps.get_model("main", "OwnerBillingAccount")
    today = django.utils.timezone.localdate()
    owner_emails = (
        Property.objects
        .exclude(owner_email="")
        .values_list("owner_email", flat=True)
        .distinct()
    )

    for owner_email in owner_emails:
        OwnerBillingAccount.objects.get_or_create(
            owner_email=owner_email,
            defaults={
                "plan": "free_trial",
                "status": "trial",
                "monthly_amount": Decimal("0.00"),
                "included_property_count": Property.objects.filter(owner_email__iexact=owner_email).count(),
                "trial_start_date": today,
                "trial_end_date": today + timedelta(days=365),
            },
        )


def remove_seeded_owner_billing_accounts(apps, schema_editor):
    OwnerBillingAccount = apps.get_model("main", "OwnerBillingAccount")
    OwnerBillingAccount.objects.filter(plan="free_trial", status="trial", monthly_amount=Decimal("0.00")).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0051_platform_revenue_settings"),
    ]

    operations = [
        migrations.CreateModel(
            name="OwnerBillingAccount",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("owner_email", models.EmailField(max_length=254, unique=True)),
                ("owner_name", models.CharField(blank=True, max_length=160)),
                ("plan", models.CharField(choices=[("free_trial", "Free Trial"), ("starter", "Starter"), ("portfolio", "Portfolio"), ("enterprise", "Enterprise / Custom")], default="free_trial", max_length=30)),
                ("status", models.CharField(choices=[("trial", "Trial"), ("active", "Active"), ("past_due", "Past Due"), ("cancelled", "Cancelled"), ("comped", "Comped")], default="trial", max_length=20)),
                ("monthly_amount", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=10)),
                ("included_property_count", models.PositiveIntegerField(default=1)),
                ("included_unit_count", models.PositiveIntegerField(default=0)),
                ("trial_start_date", models.DateField(blank=True, null=True)),
                ("trial_end_date", models.DateField(blank=True, null=True)),
                ("next_billing_date", models.DateField(blank=True, null=True)),
                ("stripe_customer_id", models.CharField(blank=True, max_length=255)),
                ("stripe_subscription_id", models.CharField(blank=True, max_length=255)),
                ("internal_notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["owner_email"],
            },
        ),
        migrations.RunPython(seed_owner_billing_accounts, remove_seeded_owner_billing_accounts),
    ]
