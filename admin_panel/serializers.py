from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Task, TaskType, Cluster

User = get_user_model()

class TaskTypeStatSerializer(serializers.Serializer):
    task_name = serializers.CharField()           # <--- changed from 'label'
    total = serializers.IntegerField()
    completed = serializers.IntegerField()
    pending = serializers.IntegerField()
    in_progress = serializers.IntegerField()      # <--- added
    color = serializers.CharField()

class ClusterStatSerializer(serializers.Serializer):
    name = serializers.CharField()
    total = serializers.IntegerField()
    completed = serializers.IntegerField()

class RecentTaskSerializer(serializers.Serializer):
    employee_name = serializers.CharField()
    task_id = serializers.CharField()
    task_type = serializers.CharField()
    global_id = serializers.CharField()

class RecentEmployeeSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    email = serializers.CharField()
    active = serializers.BooleanField()          # <--- changed from is_active to active

class DashboardStatsSerializer(serializers.Serializer):
    total_employees = serializers.IntegerField()
    total_tasks = serializers.IntegerField()
    completed_tasks = serializers.IntegerField()
    pending_tasks = serializers.IntegerField()
    in_progress_tasks = serializers.IntegerField()
    task_type_stats = TaskTypeStatSerializer(many=True)
    clusters = ClusterStatSerializer(many=True)
    recent_assigned_tasks = RecentTaskSerializer(many=True)
    recent_employees = RecentEmployeeSerializer(many=True)

# If you need a serializer for listing all employees (in the admin panel):
class EmployeeListSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'first_name', 'email', 'is_active', 'role', 'state']

class TaskListSerializer(serializers.ModelSerializer):
    task_type = serializers.CharField(source='type.name', read_only=True)
    assigned_by_name = serializers.SerializerMethodField()
    assigned_to_name = serializers.SerializerMethodField()
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
        ]

    def get_assigned_by_name(self, obj):
        return obj.assigned_by.first_name if obj.assigned_by else None

    def get_assigned_to_name(self, obj):
        return obj.assigned_to.first_name if obj.assigned_to else None
