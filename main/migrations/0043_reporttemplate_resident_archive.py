from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("main", "0042_currentresidentrosterentry_financial_terms"),
    ]

    operations = [
        migrations.AddField(
            model_name="housingapplication",
            name="archive_notes",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="housingapplication",
            name="archived_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="housingapplication",
            name="move_out_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="housingapplication",
            name="resident_file_status",
            field=models.CharField(
                choices=[("active", "Active / Current"), ("archived", "Archived / Moved Out")],
                default="active",
                max_length=30,
            ),
        ),
        migrations.CreateModel(
            name="ReportTemplate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("report_type", models.CharField(max_length=80)),
                ("start_date", models.DateField(blank=True, null=True)),
                ("end_date", models.DateField(blank=True, null=True)),
                ("financial_entry_types", models.JSONField(blank=True, default=list)),
                (
                    "math_mode",
                    models.CharField(
                        choices=[
                            ("none", "No extra math"),
                            ("sum", "Sum selected column"),
                            ("average", "Average selected column"),
                        ],
                        default="none",
                        max_length=20,
                    ),
                ),
                ("math_column", models.CharField(blank=True, max_length=120)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="custom_report_templates",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "property",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="custom_report_templates",
                        to="main.property",
                    ),
                ),
            ],
            options={
                "ordering": ["name"],
                "unique_together": {("created_by", "name")},
            },
        ),
    ]
