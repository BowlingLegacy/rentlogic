from django.db import migrations, models
import django.db.models.deletion


def populate_entry_property(apps, schema_editor):
    FinancialEntry = apps.get_model("main", "FinancialEntry")
    Property = apps.get_model("main", "Property")
    entries = FinancialEntry.objects.filter(ledger_scope="property", property__isnull=True)
    for entry in entries.select_related("upload").iterator():
        matches = Property.objects.filter(name=entry.property_name)
        if matches.count() == 1:
            entry.property_id = matches.values_list("id", flat=True).first()
            entry.save(update_fields=["property"])
        elif not entry.property_name and entry.upload.property_id:
            entry.property_id = entry.upload.property_id
            entry.save(update_fields=["property"])


class Migration(migrations.Migration):
    dependencies = [("main", "0054_alter_financialentry_property_name_and_more")]

    # BowlingLegacy 0085 owns the shared field and conservative backfill.
    operations = []
