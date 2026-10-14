from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("main", "0042_sms_delivery_status")]
    operations = [
        migrations.AddField(model_name="housingapplication", name="tenancy_status", field=models.CharField(choices=[("active", "Active Tenant"), ("former", "Former Tenant")], default="active", max_length=20)),
        migrations.AddField(model_name="housingapplication", name="move_out_date", field=models.DateField(blank=True, null=True)),
        migrations.AddField(model_name="housingapplication", name="former_tenant_archived_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="housingapplication", name="tenancy_end_reason", field=models.CharField(blank=True, max_length=255)),
        migrations.AddField(model_name="housingapplication", name="tenancy_archive_notes", field=models.TextField(blank=True)),
    ]
