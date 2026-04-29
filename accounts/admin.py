from django.contrib import admin
from .models import Profile, InviteCode


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "status", "phone")
    list_filter = ("role", "status")
    search_fields = ("user__username", "user__email", "phone")


@admin.register(InviteCode)
class InviteCodeAdmin(admin.ModelAdmin):
    list_display = ("full_name", "email", "phone", "code", "role_to_create", "is_used", "created_at")
    list_filter = ("role_to_create", "is_used")
    search_fields = ("full_name", "email", "phone", "code")
    readonly_fields = ("code", "created_at")

    # 🔥 Hides created_by from admin form
    exclude = ("created_by",)

    # 🔥 Auto-assigns who created the code
    def save_model(self, request, obj, form, change):
        if not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)