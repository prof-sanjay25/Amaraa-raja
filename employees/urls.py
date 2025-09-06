from django.urls import path
from .views import submit_report, upload_report_file, get_my_tasks, my_reports, view_my_report, get_profile, update_profile, change_password

urlpatterns = [
    path('submit-report/', submit_report),
    path('upload-report-file/', upload_report_file),
    path('my-tasks/', get_my_tasks),
    path('my-reports/', my_reports),
    path('report/<int:report_id>/', view_my_report),
    path('profile/', get_profile),
    path('update-profile/', update_profile),
    path('change-password/', change_password),
]