from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0031_propertyroomrent_deposit_paid_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="existingresidentintake",
            name="application",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="existing_resident_intake",
                to="main.housingapplication",
            ),
        ),
    ]
