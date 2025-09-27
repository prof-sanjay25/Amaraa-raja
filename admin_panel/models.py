from django.conf import settings
from django.db import models
from django.utils import timezone
from django.dispatch import receiver
from django.db.models.signals import post_save
import uuid
from superadmin.models import SiteData


class Admin(models.Model):
    USER_TYPE_CHOICES = [
        ("AREML", "AREML"),
        ("SWEAR", "SWEAR"),
        ("3rd Party", "3rd Party"),
        ("Customer", "Customer"),
    ]

    USER_ROLE_CHOICES = [
        ("DG SME", "DG SME"),
        ("AC SME", "AC SME"),
        ("circle Head", "circle Head"),
        ("IME Lead", "IME Lead"),
        ("Surveillance Lead", "Surveillance Lead"),
        ("Infra Lead", "Infra Lead"),
        ("Energy Lead", "Energy Lead"),
        ("HSSE Lead", "HSSE Lead"),
        ("Energy MIS", "Energy MIS"),
        ("Infra MIS", "Infra MIS"),
        ("Operational Lead", "Operational Lead"),
        ("Cluster Lead", "Cluster Lead"),
        ("Supervisor", "Supervisor"),
        ("Technician", "Technician"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="admin_profile",
        null=True,
        blank=True,
    )

    # ✅ With defaults so migrations won’t block
    company_name = models.CharField(max_length=255, default="Unknown Company")
    employee_id = models.CharField(max_length=50, unique=True, editable=False)
    passport_photo = models.ImageField(
        upload_to="admin/passports/", blank=True, null=True
    )
    signature_photo = models.ImageField(
        upload_to="admin/signatures/", blank=True, null=True
    )
    mobile_number = models.CharField(max_length=10, default="0000000000")  # dummy 10 digits
    user_type = models.CharField(
        max_length=50, choices=USER_TYPE_CHOICES, default="AREML"
    )
    user_role = models.CharField(
        max_length=100, choices=USER_ROLE_CHOICES, default="Technician"
    )

    # L1 User ID → Manager (can be Superadmin or higher Admin)
    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="admin_team_members",
        blank=True,
        null=True,
    )

    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.user.first_name if self.user else 'Unknown'} ({self.employee_id})"



class TaskType(models.Model):
    """
    Model representing a type/category of task (e.g., Full Services, DG PM).
    """
    name = models.CharField(max_length=100)
    color_code = models.CharField(max_length=50)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

class Cluster(models.Model):
    """
    Represents a cluster/site group.
    """
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name



class Task(models.Model):
    """
    Task assigned to an employee for a specific site and cluster.
    """
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('wait_for_review', 'Wait for Review'),
        ('completed', 'Completed'),
    )

    # 🔹 task_id auto-generated after creation
    task_id = models.CharField(max_length=100, unique=True, editable=False)
    global_id = models.CharField(max_length=100)
    title = models.CharField(max_length=200)  # e.g. "DG PM", "DG CM", etc.
    description = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    type = models.ForeignKey("TaskType", on_delete=models.CASCADE, related_name="tasks")
    cluster = models.ForeignKey("Cluster", on_delete=models.CASCADE, related_name="tasks")
    planned_date = models.DateField(null=True, blank=True)

    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="tasks"
    )
    deadline = models.DateTimeField(null=True, blank=True)
    assigned_date = models.DateTimeField(default=timezone.now)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    site = models.ForeignKey(
        "superadmin.SiteData",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="tasks"
    )
    site_name = models.CharField(max_length=255, blank=True, null=True)
    cluster_name = models.CharField(max_length=255, blank=True, null=True)

    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_tasks"
    )

    def __str__(self):
        return f"{self.task_id} - {self.title} ({self.status})"

    class Meta:
        ordering = ["-created_at"]

    @property
    def task_name(self):
        """
        Dashboard-friendly task name.
        Prioritize `title`, fallback could be `type.name` if needed.
        """
        return self.title.strip()

    @staticmethod
    def get_dashboard_counts():
        """
        Example usage for dashboard aggregation.
        Returns a dict mapping display names to counts by status.
        """
        mapping = [
            ("DG PM", "DG PM"),
            ("DG CM", "DG CM"),
            ("AC PM", "AC PM"),
            ("AC CM", "AC CM"),
            ("Site Visit", "Site Visit"),
        ]
        stats = []
        for dash_name, db_title in mapping:
            qs = Task.objects.filter(title=db_title)
            stats.append({
                "task_name": dash_name,
                "total": qs.count(),
                "completed": qs.filter(status="completed").count(),
                "pending": qs.filter(status="pending").count(),
                "wait_for_review": qs.filter(status="wait_for_review").count(), 
            })
        return stats


# 🔹 Signal to auto-generate unique task_id after creation
@receiver(post_save, sender=Task)
def set_task_id(sender, instance, created, **kwargs):
    if created and not instance.task_id:
        # Sequential style (T100001, T100002, ...)
        instance.task_id = f"T{instance.id + 100000}"
        instance.save(update_fields=["task_id"])



from django.db import models
from django.conf import settings

class AuditLog(models.Model):
    ACTION_CHOICES = [
        ("ASSIGN_TASK", "Assign Task"),
        ("UPDATE_TASK", "Update Task"),
        ("DELETE_TASK", "Delete Task"),
        ("REVIEW_REPORT", "Review Report"),
        ("APPROVE_REPORT", "Approve Report"),
        ("REJECT_REPORT", "Reject Report"),
        ("CREATE_EMPLOYEE", "Create Employee"),
        ("DELETE_EMPLOYEE", "Delete Employee"),
        ("TOGGLE_EMPLOYEE", "Toggle Employee Status"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=50, choices=ACTION_CHOICES)
    target_type = models.CharField(max_length=50)   # e.g. "Task", "Report", "Employee"
    target_id = models.CharField(max_length=100)    # task_id, report_id, employee_id
    timestamp = models.DateTimeField(auto_now_add=True)
    details = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f"{self.user} - {self.action} ({self.target_type} {self.target_id})"
