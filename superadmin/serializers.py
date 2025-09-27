# superadmin/serializers.py

from rest_framework import serializers
from authentication.models import User
from admin_panel.models import Admin  # or your Admin model path

class AdminSerializer(serializers.ModelSerializer):
    manager_email = serializers.SerializerMethodField()

    class Meta:
        model = Admin
        fields = [
            "id", "name", "email", "company_name", "circle",
            "user_type", "user_role", "is_active",
            "passport_photo", "signature_photo",
            "date_joined", "manager_id", "manager_email"  # ✅ add manager_email
        ]

    def get_manager_email(self, obj):
        return obj.manager.email if obj.manager else None
