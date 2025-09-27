from django.db import models

class SiteData(models.Model):
    """
    Holds metadata for sites.
    """
    global_id = models.CharField(max_length=100, unique=True, db_index=True)
    cluster_name = models.CharField(max_length=100)
    site_name = models.CharField(max_length=100)
    latitude = models.CharField(max_length=30, blank=True, null=True)   # keep as str if raw
    longitude = models.CharField(max_length=30, blank=True, null=True)  # or use DecimalField
    circle = models.CharField(max_length=100, blank=True, null=True, db_index=True)

    def __str__(self):
        return f"{self.global_id} - {self.site_name}"
