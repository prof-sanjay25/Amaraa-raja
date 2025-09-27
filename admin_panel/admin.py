from django.contrib import admin
from .models import  Task, TaskType, Cluster  # add other models as needed
from superadmin.models import SiteData
admin.site.register(SiteData)

