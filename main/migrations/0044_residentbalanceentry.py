import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL), ("main", "0043_housingapplication_tenancy_archive")]
    operations = [migrations.CreateModel(
        name="ResidentBalanceEntry",
        fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("entry_kind", models.CharField(choices=[("charge", "Charge"), ("credit", "Credit")], max_length=20)),
            ("balance_type", models.CharField(choices=[("rent", "Rent"), ("utility", "Utilities")], max_length=20)),
            ("amount", models.DecimalField(decimal_places=2, max_digits=10)), ("service_month", models.DateField(blank=True, null=True)),
            ("description", models.CharField(blank=True, max_length=255)), ("notes", models.TextField(blank=True)),
            ("created_at", models.DateTimeField(auto_now_add=True)),
            ("application", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="balance_entries", to="main.housingapplication")),
            ("recorded_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="resident_balance_entries", to=settings.AUTH_USER_MODEL)),
        ], options={"ordering": ["-created_at", "-id"]},
    )]
