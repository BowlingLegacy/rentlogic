from django.contrib import admin

from .models import Property, PropertyImage


class PropertyImageInline(admin.TabularInline):
    model = PropertyImage
    extra = 1


@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "availability_status", "available_date", "owner_email")
    list_filter = ("availability_status", "cable_ready")
    search_fields = ("name", "address", "owner_email")
    inlines = [PropertyImageInline]
