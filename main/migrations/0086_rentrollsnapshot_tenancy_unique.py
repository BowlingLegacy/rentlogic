from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("main", "0085_financialentry_property")]
    operations = [
        migrations.RemoveConstraint(model_name="rentrollsnapshot", name="unique_monthly_rent_roll_room"),
        migrations.AddConstraint(model_name="rentrollsnapshot", constraint=models.UniqueConstraint(fields=("property", "service_month", "room_unit_label", "application"), name="unique_monthly_rent_roll_tenancy")),
    ]
