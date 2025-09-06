from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from .models import User


class UserAdmin(BaseUserAdmin):
    list_display = (
        "username", "email", "role", "state", "is_active", "is_staff",
        "passport_thumbnail", "signature_thumbnail"
    )
    list_filter = ("role", "state", "is_active")

    fieldsets = BaseUserAdmin.fieldsets + (
        (None, {"fields": (
            "role", "global_id", "state_user_id", "state",
            "passport_photo", "signature_photo",
            "passport_preview", "signature_preview"
        )}),
    )

    readonly_fields = ("passport_preview", "signature_preview")

    # --- Thumbnails in list view ---
    def passport_thumbnail(self, obj):
        if obj.passport_photo:
            return format_html('<img src="{}" width="40" height="40" />', obj.passport_photo.url)
        return "—"
    passport_thumbnail.short_description = "Passport"

    def signature_thumbnail(self, obj):
        if obj.signature_photo:
            return format_html('<img src="{}" width="40" height="40" />', obj.signature_photo.url)
        return "—"
    signature_thumbnail.short_description = "Signature"

    # --- Large preview inside form ---
    def passport_preview(self, obj):
        if obj.passport_photo:
            return format_html('<img src="{}" width="150" />', obj.passport_photo.url)
        return "No Passport"
    passport_preview.short_description = "Passport Preview"

    def signature_preview(self, obj):
        if obj.signature_photo:
            return format_html('<img src="{}" width="150" />', obj.signature_photo.url)
        return "No Signature"
    signature_preview.short_description = "Signature Preview"


admin.site.register(User, UserAdmin)
