from decimal import Decimal
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("main", "0051_enforce_aaron_june_july_rent")]
    operations = [
        migrations.CreateModel(name="RentRollSnapshot", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("service_month", models.DateField()), ("room_unit_label", models.CharField(max_length=50)), ("resident_name", models.CharField(max_length=255)),
            ("monthly_rent", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=10)),
            ("rent_charge", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=10)),
            ("utility_monthly", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=10)),
            ("utility_charge", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=10)),
            ("deposit_required", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=10)),
            ("deposit_paid", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=10)),
            ("locked_at", models.DateTimeField(auto_now_add=True)),
            ("application", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="rent_roll_snapshots", to="main.housingapplication")),
            ("property", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="rent_roll_snapshots", to="main.property")),
        ], options={"ordering": ["property__name", "room_unit_label", "resident_name"]}),
        migrations.AddConstraint(model_name="rentrollsnapshot", constraint=models.UniqueConstraint(fields=("property", "service_month", "room_unit_label"), name="unique_monthly_rent_roll_room")),
    ]
