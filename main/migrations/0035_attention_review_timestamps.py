from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0034_payment_service_month_months_covered"),
    ]

    operations = [
        migrations.AddField(
            model_name="existingresidentintake",
            name="landlord_reviewed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="housingapplication",
            name="landlord_reviewed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
