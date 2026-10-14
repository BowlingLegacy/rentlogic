from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("main", "0040_accounting_controls")]
    operations = [
        migrations.AddField(model_name="housingapplication", name="application_folder", field=models.CharField(choices=[("active", "Active"), ("waiting", "Waiting List"), ("archived", "Archived")], default="active", max_length=20)),
        migrations.AddField(model_name="housingapplication", name="application_folder_updated_at", field=models.DateTimeField(blank=True, null=True)),
    ]
