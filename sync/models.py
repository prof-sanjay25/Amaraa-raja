from django.db import models
from authentication.models import User

class SyncConflict(models.Model):
    reported_by = models.ForeignKey(User, on_delete=models.CASCADE)
    model_name = models.CharField(max_length=100)
    local_data = models.JSONField()
    server_data = models.JSONField()
    resolved_data = models.JSONField(blank=True, null=True)
    is_resolved = models.BooleanField(default=False)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Conflict on {self.model_name} by {self.reported_by.username}"
