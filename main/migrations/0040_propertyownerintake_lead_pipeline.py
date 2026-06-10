from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0039_rental_listing_workflow"),
    ]

    operations = [
        migrations.AddField(
            model_name="propertyownerintake",
            name="follow_up_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="propertyownerintake",
            name="internal_notes",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="propertyownerintake",
            name="lead_stage",
            field=models.CharField(
                choices=[
                    ("new", "New Lead"),
                    ("contacted", "Contacted"),
                    ("demo_scheduled", "Demo Scheduled"),
                    ("onboarding", "Onboarding"),
                    ("closed_won", "Closed Won"),
                    ("closed_lost", "Closed Lost"),
                ],
                default="new",
                max_length=30,
            ),
        ),
    ]
