from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("main", "0052_owner_billing_account")]

    operations = [
        migrations.CreateModel(
            name="PropertyMembership",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("role", models.CharField(choices=[("owner", "Owner"), ("manager", "Manager")], max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("property", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="memberships", to="main.property")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="property_memberships", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddConstraint(
            model_name="propertymembership",
            constraint=models.UniqueConstraint(fields=("property", "user", "role"), name="unique_property_user_role"),
        ),
    ]
