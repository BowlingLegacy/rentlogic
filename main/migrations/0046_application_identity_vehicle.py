from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("main", "0045_accountingreceiptsplit")]
    operations = [
        migrations.AddField(model_name="housingapplication", name="identity_selfie_upload", field=models.FileField(blank=True, null=True, upload_to="application_identity_selfies/")),
        migrations.AddField(model_name="housingapplication", name="has_vehicle", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="housingapplication", name="vehicle_description", field=models.CharField(blank=True, max_length=255)),
    ]
