from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0041_accountingreceipt_ocr_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="currentresidentrosterentry",
            name="monthly_rent",
            field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=10),
        ),
        migrations.AddField(
            model_name="currentresidentrosterentry",
            name="rent_due_day",
            field=models.PositiveSmallIntegerField(default=1),
        ),
        migrations.AddField(
            model_name="currentresidentrosterentry",
            name="monthly_utilities",
            field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=10),
        ),
        migrations.AddField(
            model_name="currentresidentrosterentry",
            name="current_rent_balance",
            field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=10),
        ),
        migrations.AddField(
            model_name="currentresidentrosterentry",
            name="current_utility_balance",
            field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=10),
        ),
        migrations.AddField(
            model_name="currentresidentrosterentry",
            name="deposit_required",
            field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=10),
        ),
        migrations.AddField(
            model_name="currentresidentrosterentry",
            name="deposit_held",
            field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=10),
        ),
        migrations.AddField(
            model_name="currentresidentrosterentry",
            name="last_month_rent_paid",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="currentresidentrosterentry",
            name="last_month_rent_amount",
            field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=10),
        ),
        migrations.AddField(
            model_name="currentresidentrosterentry",
            name="outstanding_balance",
            field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=10),
        ),
    ]
