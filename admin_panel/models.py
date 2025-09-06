from django.conf import settings
from django.db import models
from django.utils import timezone
from django.dispatch import receiver
from django.db.models.signals import post_save
import uuid

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

class SiteData(models.Model):
    """
    Holds metadata for sites.
    """
    global_id = models.CharField(max_length=100, unique=True)
    cluster_name = models.CharField(max_length=100)
    site_name = models.CharField(max_length=100)
    latitude = models.CharField(max_length=30, blank=True, null=True)
    longitude = models.CharField(max_length=30, blank=True, null=True)

    def __str__(self):
        return f"{self.global_id} - {self.site_name}"

class Task(models.Model):
    """
    Task assigned to an employee for a specific site and cluster.
    """
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
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
        "SiteData",
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
                "in_progress": qs.filter(status="in_progress").count(),
            })
        return stats


# 🔹 Signal to auto-generate unique task_id after creation
@receiver(post_save, sender=Task)
def set_task_id(sender, instance, created, **kwargs):
    if created and not instance.task_id:
        # Sequential style (T100001, T100002, ...)
        instance.task_id = f"T{instance.id + 100000}"
        instance.save(update_fields=["task_id"])