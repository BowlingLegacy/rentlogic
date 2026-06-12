from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("main", "0043_reporttemplate_resident_archive"),
    ]

    operations = [
        migrations.AlterField(
            model_name="housingapplication",
            name="resident_file_status",
            field=models.CharField(
                choices=[
                    ("active", "Active / Current"),
                    ("archived", "Archived / Moved Out"),
                    ("unit_file", "Empty Unit File"),
                ],
                default="active",
                max_length=30,
            ),
        ),
        migrations.AddField(
            model_name="applicantdocument",
            name="ocr_error",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="applicantdocument",
            name="ocr_processed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="applicantdocument",
            name="ocr_status",
            field=models.CharField(
                choices=[
                    ("not_processed", "Not Processed"),
                    ("extracted", "Text Extracted"),
                    ("needs_ocr_provider", "Needs OCR Provider"),
                    ("failed", "OCR Failed"),
                ],
                default="not_processed",
                max_length=30,
            ),
        ),
        migrations.AddField(
            model_name="applicantdocument",
            name="ocr_suggested_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="applicantdocument",
            name="ocr_suggested_name",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="applicantdocument",
            name="ocr_suggested_unit",
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.AddField(
            model_name="applicantdocument",
            name="ocr_text",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="applicantdocument",
            name="packet_notes",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="applicantdocument",
            name="packet_reviewed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="applicantdocument",
            name="packet_upload",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="applicantdocument",
            name="packet_reviewed_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="reviewed_tenant_file_packets",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
