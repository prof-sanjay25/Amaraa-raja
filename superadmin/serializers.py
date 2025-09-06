from rest_framework import serializers
from authentication.models import User
from reports.models import Report
from sync.models import SyncConflict
from admin_panel.models import Task


# ✅ Admin Serializer (used by SuperAdmin only)
class AdminUserSerializer(serializers.ModelSerializer):
    global_id = serializers.ReadOnlyField()
    state_user_id = serializers.ReadOnlyField()
    username = serializers.ReadOnlyField()

    class Meta:
        model = User
        fields = [
            'id', 'global_id', 'state_user_id', 'username',
            'email', 'first_name', 'last_name', 'state', 'is_active'
        ]
        read_only_fields = ['id', 'global_id', 'state_user_id', 'username']


# ✅ Employee Serializer (used by SuperAdmin and Admin)
class EmployeeUserSerializer(serializers.ModelSerializer):
    global_id = serializers.ReadOnlyField()
    state_user_id = serializers.ReadOnlyField()
    username = serializers.ReadOnlyField()

    class Meta:
        model = User
        fields = [
            'id', 'global_id', 'state_user_id', 'username',
            'email', 'first_name', 'last_name', 'state', 'is_active'
        ]
        read_only_fields = ['id', 'global_id', 'state_user_id', 'username']


# ✅ Report Serializer
class ReportSerializer(serializers.ModelSerializer):
    submitted_by = serializers.StringRelatedField()

    class Meta:
        model = Report
        fields = [
            'id', 'submitted_by', 'status', 'data',
            'submitted_at', 'rejection_reason'
        ]


# ✅ Conflict Resolution Serializer
class ConflictSerializer(serializers.ModelSerializer):
    reported_by = serializers.StringRelatedField()

    class Meta:
        model = SyncConflict
        fields = [
            'id', 'reported_by', 'model_name',
            'local_data', 'server_data',
            'resolved_data', 'is_resolved', 'timestamp'
        ]


# ✅ SuperAdmin Profile Serializer (no state)
class SuperAdminProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name']
        read_only_fields = ['id', 'username']
