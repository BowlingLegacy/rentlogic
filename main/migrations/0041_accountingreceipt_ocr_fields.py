from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0040_propertyownerintake_lead_pipeline"),
    ]

    operations = [
        migrations.AddField(
            model_name="accountingreceipt",
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
            model_name="accountingreceipt",
            name="ocr_text",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="accountingreceipt",
            name="ocr_error",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="accountingreceipt",
            name="ocr_processed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="accountingreceipt",
            name="ocr_suggested_vendor",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="accountingreceipt",
            name="ocr_suggested_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="accountingreceipt",
            name="ocr_suggested_amount",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True),
        ),
    ]
