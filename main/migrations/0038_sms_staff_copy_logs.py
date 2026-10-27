import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("main", "0037_property_utility_setup")]
    operations = [
        migrations.AlterField(model_name="smsmessagelog", name="application", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="sms_logs", to="main.housingapplication")),
        migrations.AddField(model_name="smsmessagelog", name="recipient_label", field=models.CharField(blank=True, max_length=255)),
    ]
