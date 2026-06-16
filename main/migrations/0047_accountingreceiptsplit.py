from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0046_user_code_activation_timestamps"),
    ]

    operations = [
        migrations.CreateModel(
            name="AccountingReceiptSplit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("entry_type", models.CharField(choices=[("operating_expense", "Operating Expense"), ("debt_service", "Debt Service"), ("capital_expense", "Capital Expense"), ("other", "Other")], default="operating_expense", max_length=50)),
                ("description", models.TextField(blank=True)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("category", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="receipt_splits", to="main.expensecategory")),
                ("financial_entry", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="source_receipt_split", to="main.financialentry")),
                ("receipt", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="splits", to="main.accountingreceipt")),
            ],
            options={
                "ordering": ["id"],
            },
        ),
    ]
