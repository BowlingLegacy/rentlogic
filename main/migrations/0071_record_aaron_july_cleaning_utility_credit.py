"""Compatibility marker for a BowlingLegacy production-only data migration.

RentalReadyPro records the exact migration identity but deliberately does not
replay customer-specific historical corrections on new databases.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("main", "0070_record_aaron_july_maintenance_credit")]
    operations = []
