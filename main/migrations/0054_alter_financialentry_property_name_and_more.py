from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("main", "0053_property_membership")]

    operations = [
        migrations.AlterField(
            model_name="financialentry",
            name="property_name",
            field=models.CharField(blank=True, default="Rental Property", max_length=255),
        ),
        migrations.AlterField(
            model_name="signeddocument",
            name="document_type",
            field=models.CharField(
                choices=[
                    ("lease", "Resident Lease Agreement"),
                    ("emergency_contact", "Emergency Contact Form"),
                    ("painted_lady_acknowledgment", "Property Acknowledgment"),
                    ("lead_disclosure", "Lead Disclosure"),
                    ("asbestos_disclosure", "Asbestos Disclosure"),
                    ("house_rules", "House Rules"),
                    ("other", "Other"),
                ],
                default="other",
                max_length=50,
            ),
        ),
        migrations.AlterField(
            model_name="stripepaymentconfiguration",
            name="account_mode",
            field=models.CharField(
                choices=[
                    ("platform", "Use RentalReadyPro platform Stripe account"),
                    ("owner_connect", "Use one owner Stripe account for multiple properties"),
                    ("property_connect", "Use this property's own Stripe account"),
                    ("manual", "Manual/offline payments only"),
                ],
                default="platform",
                max_length=30,
            ),
        ),
    ]
