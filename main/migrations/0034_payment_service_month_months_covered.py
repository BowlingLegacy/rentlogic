from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0033_housingapplication_move_in_charges"),
    ]

    operations = [
        migrations.AddField(
            model_name="payment",
            name="months_covered",
            field=models.PositiveSmallIntegerField(default=1),
        ),
        migrations.AddField(
            model_name="payment",
            name="service_month",
            field=models.DateField(
                blank=True,
                help_text="First day of the month this payment applies to for rent roll and T-12 reporting.",
                null=True,
            ),
        ),
    ]
