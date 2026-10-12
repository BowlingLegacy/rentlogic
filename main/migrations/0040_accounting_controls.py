import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("main", "0039_merge_20260608_0614"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(
            name="AccountingPeriod",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("month", models.PositiveSmallIntegerField()), ("year", models.PositiveIntegerField()),
                ("status", models.CharField(choices=[("open", "Open"), ("closed", "Closed")], default="open", max_length=20)),
                ("closed_at", models.DateTimeField(blank=True, null=True)), ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
                ("closed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="closed_accounting_periods", to=settings.AUTH_USER_MODEL)),
                ("property", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="accounting_periods", to="main.property")),
            ],
            options={"ordering": ("-year", "-month", "property__name"), "unique_together": {("property", "month", "year")}},
        ),
        migrations.CreateModel(
            name="VendorCategoryRule",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("vendor_contains", models.CharField(max_length=255)),
                ("entry_type", models.CharField(choices=[("operating_expense", "Operating Expense"), ("debt_service", "Debt Service"), ("capital_expense", "Capital Expense"), ("other", "Other")], default="operating_expense", max_length=50)),
                ("description_template", models.CharField(blank=True, max_length=255)), ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
                ("category", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="vendor_rules", to="main.expensecategory")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_vendor_category_rules", to=settings.AUTH_USER_MODEL)),
                ("property", models.ForeignKey(blank=True, help_text="Leave blank to use this rule for every property.", null=True, on_delete=django.db.models.deletion.CASCADE, related_name="vendor_category_rules", to="main.property")),
            ],
            options={"ordering": ("property__name", "vendor_contains"), "unique_together": {("property", "vendor_contains")}},
        ),
    ]
