from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Task, TaskType, Cluster

User = get_user_model()


class TaskTypeStatSerializer(serializers.Serializer):
    task_name = serializers.CharField()
    total = serializers.IntegerField()
    completed = serializers.IntegerField()
    pending = serializers.IntegerField()
    wait_for_review = serializers.IntegerField()
    color = serializers.CharField()


class ClusterStatSerializer(serializers.Serializer):
    cluster__id = serializers.IntegerField()
    cluster__name = serializers.CharField()
    total = serializers.IntegerField()
    completed = serializers.IntegerField()
    pending = serializers.IntegerField()
    wait_for_review = serializers.IntegerField()


class RecentTaskSerializer(serializers.Serializer):
    employee_name = serializers.CharField()
    task_id = serializers.CharField()
    task_type = serializers.CharField()
    global_id = serializers.CharField()

class RecentEmployeeSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    email = serializers.CharField()
    active = serializers.BooleanField()


class TrendSerializer(serializers.Serializer):
    date = serializers.CharField()
    title = serializers.CharField()
    status = serializers.CharField()
    total = serializers.IntegerField()


class DashboardStatsSerializer(serializers.Serializer):
    total_employees = serializers.IntegerField()
    total_tasks = serializers.IntegerField()
    completed_tasks = serializers.IntegerField()
    pending_tasks = serializers.IntegerField()
    wait_for_review_tasks = serializers.IntegerField()
    task_type_stats = TaskTypeStatSerializer(many=True)
    clusters = ClusterStatSerializer(many=True)
    recent_assigned_tasks = RecentTaskSerializer(many=True)
    recent_employees = RecentEmployeeSerializer(many=True)
    daily_trends = TrendSerializer(many=True, required=False)
    monthly_trends = TrendSerializer(many=True, required=False)



User = get_user_model()


class EmployeeListSerializer(serializers.ModelSerializer):
    passport_photo = serializers.SerializerMethodField()
    signature_photo = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id',
            'first_name',
            'email',
            'is_active',
            'role',
            'circle',           # ✅ circle instead of state
            'passport_photo',   # ✅ new
            'signature_photo',  # ✅ new
        ]

    def get_passport_photo(self, obj):
        try:
            if hasattr(obj, "employee_profile") and obj.employee_profile.passport_photo:
                request = self.context.get("request")
                url = obj.employee_profile.passport_photo.url
                return request.build_absolute_uri(url) if request else url
        except Exception:
            return None
        return None

    def get_signature_photo(self, obj):
        try:
            if hasattr(obj, "employee_profile") and obj.employee_profile.signature_photo:
                request = self.context.get("request")
                url = obj.employee_profile.signature_photo.url
                return request.build_absolute_uri(url) if request else url
        except Exception:
            return None
        return None



class TaskListSerializer(serializers.ModelSerializer):
    task_type = serializers.CharField(source='type.name', read_only=True)
    assigned_by_name = serializers.SerializerMethodField()
    assigned_to_name = serializers.SerializerMethodField()
    site_lat = serializers.SerializerMethodField()
    site_lon = serializers.SerializerMethodField()

    class Meta:
        model = Task
        fields = [
            'task_id',
            'title',
            'description',
            'status',
            'task_type',
            'site_name',
            'cluster_name',
            'assigned_date',
            'deadline',
            'assigned_by_name',
            'assigned_to_name',
            'global_id',
            'site_lat',
            'site_lon',
        ]

    def get_assigned_by_name(self, obj):
        return obj.assigned_by.first_name if obj.assigned_by else None

    def get_assigned_to_name(self, obj):
        return obj.assigned_to.first_name if obj.assigned_to else None

    def get_site_lat(self, obj):
        return float(obj.site.latitude) if obj.site and obj.site.latitude else None

    def get_site_lon(self, obj):
        return float(obj.site.longitude) if obj.site and obj.site.longitude else None

