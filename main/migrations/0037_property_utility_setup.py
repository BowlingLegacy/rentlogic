from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0036_propertyownerintake_desired_reports"),
    ]

    operations = [
        migrations.CreateModel(
            name="PropertyUtilityVendor",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("service_type", models.CharField(max_length=80)),
                ("provider_name", models.CharField(max_length=255)),
                ("setup_url", models.URLField(blank=True)),
                ("phone", models.CharField(blank=True, max_length=50)),
                ("notes", models.TextField(blank=True)),
                ("is_active", models.BooleanField(default=True)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("property", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="utility_vendors", to="main.property")),
            ],
            options={
                "ordering": ["property__name", "sort_order", "service_type", "provider_name"],
                "unique_together": {("property", "service_type", "provider_name")},
            },
        ),
        migrations.AddField(
            model_name="propertyownerintake",
            name="tenant_utility_setup_notes",
            field=models.TextField(
                blank=True,
                help_text="Utility accounts tenants must set up, with vendor names, links, phones, or notes.",
            ),
        ),
        migrations.CreateModel(
            name="ResidentUtilitySetup",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("opened_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("application", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="utility_setups", to="main.housingapplication")),
                ("vendor", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="resident_setups", to="main.propertyutilityvendor")),
            ],
            options={
                "ordering": ["vendor__sort_order", "vendor__service_type", "vendor__provider_name"],
                "unique_together": {("application", "vendor")},
            },
        ),
    ]
