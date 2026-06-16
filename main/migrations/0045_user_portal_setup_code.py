from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0044_applicantdocument_packet_ocr"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="portal_setup_code",
            field=models.CharField(blank=True, max_length=10, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="user",
            name="portal_setup_code_created_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="user",
            name="portal_setup_code_used_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
