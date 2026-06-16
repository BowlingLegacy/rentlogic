from django.db import migrations


STANDARD_EXPENSE_CATEGORIES = [
    ("Cleaning Supplies", "operating_expense"),
    ("Maintenance Supplies", "operating_expense"),
    ("Office Supplies", "operating_expense"),
    ("Power", "operating_expense"),
    ("Gas", "operating_expense"),
    ("Water", "operating_expense"),
    ("Sewer", "operating_expense"),
    ("Trash", "operating_expense"),
    ("Internet", "operating_expense"),
    ("Cable", "operating_expense"),
    ("House Phone", "operating_expense"),
    ("Account Fees", "operating_expense"),
    ("Pest Control", "operating_expense"),
    ("Insurance", "operating_expense"),
    ("Landscaping", "operating_expense"),
    ("Room Furnishings", "operating_expense"),
    ("Debt Service", "debt_service"),
    ("Capital Improvements", "capital_expense"),
]


def seed_categories(apps, schema_editor):
    ExpenseCategory = apps.get_model("main", "ExpenseCategory")

    for name, entry_type in STANDARD_EXPENSE_CATEGORIES:
        category, created = ExpenseCategory.objects.get_or_create(
            name=name,
            defaults={
                "entry_type": entry_type,
                "is_active": True,
            },
        )
        if not created and (category.entry_type != entry_type or not category.is_active):
            category.entry_type = entry_type
            category.is_active = True
            category.save(update_fields=["entry_type", "is_active"])


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0047_accountingreceiptsplit"),
    ]

    operations = [
        migrations.RunPython(seed_categories, migrations.RunPython.noop),
    ]
