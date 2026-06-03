from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0035_attention_review_timestamps"),
    ]

    operations = [
        migrations.AddField(
            model_name="propertyownerintake",
            name="desired_reports",
            field=models.TextField(blank=True),
        ),
    ]
