from decimal import Decimal

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0038_applicant_screening_workflow"),
    ]

    operations = [
        migrations.CreateModel(
            name="RentalListing",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("unit_label", models.CharField(blank=True, max_length=80)),
                ("headline", models.CharField(max_length=180)),
                ("rent_amount", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=10)),
                ("deposit_amount", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=10)),
                ("utilities_description", models.CharField(blank=True, max_length=255)),
                ("lease_terms", models.CharField(blank=True, max_length=255)),
                ("available_date", models.DateField(blank=True, null=True)),
                ("bedrooms", models.CharField(blank=True, max_length=50)),
                ("bathrooms", models.CharField(blank=True, max_length=50)),
                ("square_feet", models.PositiveIntegerField(blank=True, null=True)),
                ("unit_layout_description", models.TextField(blank=True)),
                ("property_benefits", models.TextField(blank=True)),
                ("amenities", models.TextField(blank=True)),
                ("screening_summary", models.TextField(blank=True)),
                ("listing_body", models.TextField(blank=True)),
                ("status", models.CharField(choices=[("draft", "Draft"), ("published", "Published"), ("paused", "Paused"), ("filled", "Filled"), ("archived", "Archived")], default="draft", max_length=20)),
                ("published_at", models.DateTimeField(blank=True, null=True)),
                ("filled_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_rental_listings", to=settings.AUTH_USER_MODEL)),
                ("property", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="rental_listings", to="main.property")),
            ],
            options={
                "ordering": ["-updated_at"],
            },
        ),
        migrations.CreateModel(
            name="RentalListingPhoto",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("image", models.ImageField(upload_to="rental_listing_photos/")),
                ("caption", models.CharField(blank=True, max_length=255)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("listing", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="photos", to="main.rentallisting")),
            ],
            options={
                "ordering": ["sort_order", "id"],
            },
        ),
        migrations.CreateModel(
            name="RentalListingChannel",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("channel", models.CharField(choices=[("rental_ledger", "RentalReadyPro Public Listing"), ("facebook_marketplace", "Facebook Marketplace"), ("craigslist", "Craigslist"), ("zillow", "Zillow Rental Network"), ("apartments_com", "Apartments.com"), ("yard_sign", "Yard Sign / QR Code"), ("other", "Other")], max_length=40)),
                ("status", models.CharField(choices=[("not_started", "Not Started"), ("ready", "Ready To Post"), ("posted", "Posted"), ("needs_update", "Needs Update"), ("removed", "Removed"), ("blocked", "Blocked / Not Available")], default="not_started", max_length=30)),
                ("external_url", models.URLField(blank=True)),
                ("notes", models.TextField(blank=True)),
                ("posted_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("listing", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="channels", to="main.rentallisting")),
            ],
            options={
                "ordering": ["channel"],
                "unique_together": {("listing", "channel")},
            },
        ),
    ]
