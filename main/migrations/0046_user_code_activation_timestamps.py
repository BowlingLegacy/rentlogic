from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0045_user_portal_setup_code"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="invite_code_activated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="user",
            name="portal_setup_code_activated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
