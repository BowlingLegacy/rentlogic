import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("main", "0037_property_utility_setup")]
    operations = [
        migrations.AlterField(
            model_name="existingresidentintake",
            name="application",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="existing_resident_intakes", to="main.housingapplication"),
        )
    ]
