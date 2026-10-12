from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("main", "0041_housingapplication_application_folder")]
    operations = [
        migrations.AddField(model_name="smsmessagelog", name="delivery_updated_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="smsmessagelog", name="provider_status", field=models.CharField(blank=True, max_length=100)),
        migrations.AlterField(model_name="smsmessagelog", name="status", field=models.CharField(choices=[("not_configured", "Provider Not Configured"), ("skipped_no_consent", "Skipped - No Consent"), ("queued", "Queued"), ("sent", "Accepted by Provider"), ("delivered", "Delivered"), ("undelivered", "Undelivered"), ("failed", "Failed")], default="queued", max_length=30)),
    ]
