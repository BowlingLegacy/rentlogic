from django.db import migrations, models


PAYMENT_CHOICES = [("stripe_card", "Stripe Card"), ("stripe_cashapp", "Stripe Cash App Pay"), ("bank_transfer", "Bank Transfer"), ("cashapp", "Cash App"), ("cash", "Cash"), ("check", "Check"), ("money_order", "Money Order"), ("zelle", "Zelle"), ("ach", "ACH"), ("service_credit", "Service / Labor Credit"), ("other", "Other")]


class Migration(migrations.Migration):
    dependencies = [("main", "0068_correct_chris_a_honey_rent")]
    operations = [
        migrations.AlterField(model_name="payment", name="payment_method", field=models.CharField(choices=PAYMENT_CHOICES, default="stripe_card", max_length=30)),
        migrations.AlterField(model_name="accountingreceipt", name="payment_method", field=models.CharField(choices=PAYMENT_CHOICES, default="other", max_length=30)),
    ]
