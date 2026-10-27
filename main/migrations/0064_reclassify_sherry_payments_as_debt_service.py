"""Compatibility marker for a BowlingLegacy production-only data migration.

RentalReadyPro records the exact migration identity but deliberately does not
replay customer-specific historical corrections on new databases.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("main", "0063_correct_rooms_i_and_j_occupancy")]
    operations = []
