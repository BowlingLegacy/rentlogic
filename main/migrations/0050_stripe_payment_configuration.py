from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0049_currentresidentrosterentry_sms_consent"),
    ]

    operations = [
        migrations.CreateModel(
            name="StripePaymentConfiguration",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("owner_email", models.EmailField(blank=True, help_text="Owner login email this Stripe setup belongs to.", max_length=254)),
                (
                    "account_mode",
                    models.CharField(
                        choices=[
                            ("platform", "Use Rental Ledger platform Stripe account"),
                            ("owner_connect", "Use one owner Stripe account for multiple properties"),
                            ("property_connect", "Use this property's own Stripe account"),
                            ("manual", "Manual/offline payments only"),
                        ],
                        default="platform",
                        max_length=30,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("not_started", "Not Started"),
                            ("pending", "Pending Setup"),
                            ("active", "Active"),
                            ("disabled", "Disabled"),
                        ],
                        default="not_started",
                        max_length=20,
                    ),
                ),
                ("stripe_account_id", models.CharField(blank=True, help_text="Stripe Connect account ID, such as acct_123. Do not store secret keys here.", max_length=255)),
                ("display_name", models.CharField(blank=True, max_length=255)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "property",
                    models.OneToOneField(
                        blank=True,
                        help_text="Leave blank for an owner-level default used by multiple properties.",
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="stripe_payment_configuration",
                        to="main.property",
                    ),
                ),
            ],
            options={
                "ordering": ["owner_email", "property__name", "id"],
            },
        ),
        migrations.AddField(
            model_name="payment",
            name="stripe_destination_account",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="payment",
            name="stripe_payment_configuration",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="payments", to="main.stripepaymentconfiguration"),
        ),
    ]
