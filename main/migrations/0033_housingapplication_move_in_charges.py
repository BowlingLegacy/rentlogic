from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0032_existingresidentintake_application"),
    ]

    operations = [
        migrations.AddField(
            model_name="housingapplication",
            name="move_in_rent_charge",
            field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=10),
        ),
        migrations.AddField(
            model_name="housingapplication",
            name="move_in_utility_charge",
            field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=10),
        ),
    ]
