"""Compatibility marker for a BowlingLegacy production-only data migration.

RentalReadyPro records the exact migration identity but deliberately does not
replay customer-specific historical corrections on new databases.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("main", "0075_retry_split_september_charter_receipt")]
    operations = []
