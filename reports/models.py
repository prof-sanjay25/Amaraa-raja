# from django.db import models
# from django.conf import settings
# from django.utils import timezone

# class Report(models.Model):
#     STATUS_CHOICES = (
#         ('in_progress', 'In Progress'),
#         ('pending', 'Pending'),   # If needed
#         ('approved', 'Approved'),
#         ('rejected', 'Rejected'),
#     )

#     task = models.ForeignKey(
#         'admin_panel.Task',  # Adjust if your Task model is in another app
#         on_delete=models.CASCADE,
#         related_name='reports'
#     )
#     submitted_by = models.ForeignKey(
#         settings.AUTH_USER_MODEL,
#         on_delete=models.CASCADE,
#         related_name='submitted_reports'
#     )
#     data = models.JSONField(default=dict)   # Holds the form fields as JSON
#     status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='in_progress')
#     submitted_at = models.DateTimeField(default=timezone.now)
#     approved_at = models.DateTimeField(null=True, blank=True)
#     rejection_reason = models.TextField(blank=True, null=True)

#     def __str__(self):
#         return f'Report #{self.id} for Task {self.task.task_id} by {self.submitted_by}'

#     @property
#     def files(self):
#         # Returns all files attached to this report
#         return self.reportfileupload_set.all()


# class ReportFileUpload(models.Model):
#     report = models.ForeignKey(
#         Report,
#         on_delete=models.CASCADE,
#         related_name='files'
#     )
#     field_label = models.CharField(max_length=255, blank=True, null=True)
#     file = models.FileField(upload_to='report_files/')
#     uploaded_by = models.ForeignKey(
#         settings.AUTH_USER_MODEL,
#         on_delete=models.CASCADE,
#         related_name='uploaded_report_files'
#     )
#     uploaded_at = models.DateTimeField(auto_now_add=True)

#     def __str__(self):
#         return f'File {self.file.name} for Report #{self.report.id}'



from django.db import models
from django.conf import settings
from django.utils import timezone

# Import User and Task models using get_user_model for flexibility (recommended in Django)
from django.contrib.auth import get_user_model
User = get_user_model()

# If Task model is in another app (like admin_panel), import accordingly:
from admin_panel.models import Task

class Report(models.Model):
    STATUS_CHOICES = [
        ('in_progress', 'In Progress'),
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name='reports'
    )
    submitted_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='submitted_reports'
    )
    data = models.JSONField(default=dict)   # Dynamic answers (form fields)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='in_progress'
    )
    rejection_reason = models.TextField(blank=True, null=True)
    submitted_at = models.DateTimeField(default=timezone.now)
    approved_at = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return f"Report #{self.id} for Task {self.task.task_id}"

    @property
    def files(self):
        # Returns all files attached to this report
        return self.reportfileupload_set.all()


class ReportFileUpload(models.Model):
    report = models.ForeignKey(
        Report,
        on_delete=models.CASCADE,
        related_name='files'
    )
    field_label = models.CharField(max_length=255, blank=True, null=True)
    file = models.FileField(upload_to='report_uploads/')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    uploaded_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='uploaded_report_files',
        null=True,
        blank=True
    )

    def __str__(self):
        return f"File {self.file.name} for Report #{self.report.id}"
