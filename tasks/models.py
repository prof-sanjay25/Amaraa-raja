# from django.db import models
# from authentication.models import User
# from admin_panel.models import SiteData  # ← import SiteData
# from django.utils import timezone

# class Task(models.Model):
#     task_id = models.PositiveIntegerField(unique=True)

#     # Link to site
#     site = models.ForeignKey(SiteData, on_delete=models.SET_NULL, null=True, blank=True, related_name='tasks')

#     # These remain for redundancy and reporting
#     global_id = models.CharField(max_length=100)
#     cluster_name = models.CharField(max_length=255)
#     site_name = models.CharField(max_length=255)
#     latitude = models.FloatField(null=True, blank=True)
#     longitude = models.FloatField(null=True, blank=True)

#     assigned_to = models.ForeignKey(User, on_delete=models.CASCADE)
    
    
    
#     assigned_date = models.DateTimeField(default=timezone.now)
#     state = models.CharField(max_length=100)

#     def __str__(self):
#         return f"Task {self.task_id} - {self.task_type} - {self.site_name}"
