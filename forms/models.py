from django.db import models

class FormTemplate(models.Model):
    TASK_GROUP_CHOICES = [
        ('dg', 'DG Maintenance'),
        ('ac', 'AC Maintenance'),
        ('site_visit', 'Site Visit')
    ]

    task_group = models.CharField(max_length=20, choices=TASK_GROUP_CHOICES, unique=True)
    schema = models.JSONField(default=list)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.task_group
