from django.contrib import admin

from .models import HousingApplication


@admin.register(HousingApplication)
class HousingApplicationAdmin(admin.ModelAdmin):
    list_display = ("full_name", "property", "status", "monthly_rent", "created_at")
    list_filter = ("status", "property")
    search_fields = ("full_name", "email", "phone", "space_label")
