from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0048_seed_standard_expense_categories"),
    ]

    operations = [
        migrations.AddField(
            model_name="currentresidentrosterentry",
            name="sms_consent",
            field=models.BooleanField(default=False),
        ),
    ]
