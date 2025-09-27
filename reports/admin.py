from django.contrib import admin
from .models import Report, ReportFileUpload

class ReportFileUploadInline(admin.TabularInline):
    model = ReportFileUpload
    extra = 0

@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ('id', 'task', 'submitted_by', 'status', 'submitted_at', 'approved_at')
    list_filter = ('status', 'submitted_at', 'approved_at')
    search_fields = ('task__task_id', 'submitted_by__email', 'submitted_by__first_name')
    inlines = [ReportFileUploadInline]

@admin.register(ReportFileUpload)
class ReportFileUploadAdmin(admin.ModelAdmin):
    list_display = ('id', 'report', 'field_label', 'file', 'uploaded_by', 'uploaded_at')
    search_fields = ('field_label', 'file', 'uploaded_by__email')
