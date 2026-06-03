from django.conf import settings
from django.db import models


class Property(models.Model):
    AVAILABILITY_CHOICES = [
        ("available", "Available Now"),
        ("waitlist", "Waitlist Open"),
        ("full", "Currently Full"),
    ]

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="properties",
    )
    name = models.CharField(max_length=255)
    address = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    photo = models.ImageField(upload_to="property_photos/", blank=True, null=True)
    owner_email = models.EmailField(blank=True)
    unit_size = models.CharField(max_length=100, blank=True)
    cable_ready = models.BooleanField(default=True)
    available_date = models.DateField(blank=True, null=True)
    deposit_amount = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    utilities_cost = models.CharField(max_length=255, blank=True)
    availability_status = models.CharField(
        max_length=20,
        choices=AVAILABILITY_CHOICES,
        default="full",
    )
    availability_message = models.CharField(
        max_length=255,
        default="Join Waitlist for Availability",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Properties"
        ordering = ["name"]

    def __str__(self):
        return self.name


class PropertyImage(models.Model):
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="property_gallery/")
    caption = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return f"{self.property.name} Image"
