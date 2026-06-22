from decimal import Decimal

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0037_property_utility_setup"),
    ]

    operations = [
        migrations.AddField(
            model_name="property",
            name="screening_admin_fee",
            field=models.DecimalField(blank=True, decimal_places=2, default=Decimal("0.00"), help_text="Optional client-facing admin fee. Do not charge renters on RentalReadyPro's behalf.", max_digits=10),
        ),
        migrations.AddField(
            model_name="property",
            name="screening_criteria",
            field=models.TextField(blank=True, help_text="Written applicant screening criteria shown to owners and used for consistent review."),
        ),
        migrations.AddField(
            model_name="property",
            name="screening_fee_disclosure",
            field=models.TextField(blank=True, help_text="Property-specific fee and screening disclosure shown before application submission."),
        ),
        migrations.AddField(
            model_name="property",
            name="screening_provider_cost",
            field=models.DecimalField(blank=True, decimal_places=2, default=Decimal("0.00"), max_digits=10),
        ),
        migrations.AddField(
            model_name="property",
            name="screening_provider_name",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="housingapplication",
            name="background_report",
            field=models.FileField(blank=True, null=True, upload_to="background_reports/"),
        ),
        migrations.AddField(
            model_name="housingapplication",
            name="background_report_received_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="housingapplication",
            name="owner_decision_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="housingapplication",
            name="owner_decision_notes",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="housingapplication",
            name="owner_final_decision",
            field=models.CharField(choices=[("pending", "Pending Owner Review"), ("approved", "Approved"), ("approved_conditions", "Approved With Conditions"), ("declined", "Declined"), ("withdrawn", "Withdrawn")], default="pending", max_length=30),
        ),
        migrations.AddField(
            model_name="housingapplication",
            name="screening_consent",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="housingapplication",
            name="screening_consent_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="housingapplication",
            name="screening_provider_name",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="housingapplication",
            name="screening_rating",
            field=models.CharField(choices=[("unrated", "Unrated"), ("strong", "Strong Candidate"), ("qualified", "Qualified"), ("review", "Needs Review"), ("high_risk", "High Risk"), ("declined", "Decline Recommended")], default="unrated", max_length=30),
        ),
        migrations.AddField(
            model_name="housingapplication",
            name="screening_review_summary",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="housingapplication",
            name="screening_score",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="applicantdocument",
            name="document_type",
            field=models.CharField(choices=[("lease", "Lease Agreement"), ("application_pdf", "Application PDF"), ("screening_criteria", "Screening Criteria"), ("background_report", "Background Report"), ("adverse_action_notice", "Adverse Action Notice"), ("id", "Identification"), ("income", "Proof of Income"), ("bank", "Bank Statement / Deposit Verification"), ("onboarding", "Onboarding Document"), ("other", "Other")], default="other", max_length=50),
        ),
        migrations.CreateModel(
            name="AdverseActionNotice",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("action_type", models.CharField(choices=[("declined", "Application Declined"), ("approved_conditions", "Approved With Conditions"), ("other", "Other Adverse Action")], default="declined", max_length=30)),
                ("reasons", models.TextField()),
                ("screening_company_name", models.CharField(blank=True, max_length=255)),
                ("screening_company_contact", models.TextField(blank=True)),
                ("owner_landlord_name", models.CharField(blank=True, max_length=255)),
                ("owner_landlord_contact", models.TextField(blank=True)),
                ("notice_body", models.TextField(blank=True)),
                ("sent_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("application", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="adverse_action_notices", to="main.housingapplication")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_adverse_action_notices", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
    ]
