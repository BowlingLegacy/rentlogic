from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0046_user_code_activation_timestamps"),
    ]

    # BowlingLegacy 0045 owns the shared table and state. Keeping this exact
    # identity as a marker preserves RentalReadyPro's recorded branch without
    # attempting a second CREATE TABLE.
    operations = []
