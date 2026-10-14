import django.db.models.deletion
from django.db import migrations, models


def populate_entry_property(apps, schema_editor):
    FinancialEntry = apps.get_model("main", "FinancialEntry")
    Property = apps.get_model("main", "Property")
    for entry in FinancialEntry.objects.filter(ledger_scope="property", property__isnull=True).select_related("upload").iterator():
        matches = Property.objects.filter(name=entry.property_name)
        if matches.count() == 1:
            entry.property_id = matches.values_list("id", flat=True).first()
            entry.save(update_fields=["property"])
        elif not entry.property_name and entry.upload.property_id:
            entry.property_id = entry.upload.property_id
            entry.save(update_fields=["property"])


class Migration(migrations.Migration):
    dependencies = [("main", "0084_correct_jeffery_bowling_year")]
    operations = [
        migrations.AddField(model_name="financialentry", name="property", field=models.ForeignKey(blank=True, help_text="Stable row-level property attribution; company rows remain blank.", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="financial_entries", to="main.property")),
        migrations.RunPython(populate_entry_property, migrations.RunPython.noop),
    ]
