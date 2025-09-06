from django.urls import path
from .views import (
    superadmin_dashboard_api,
    manage_admins, update_delete_admin,
    manage_employees, update_delete_employee,
    list_reports, approve_report, reject_report,
    list_conflicts, resolve_conflict,
    view_profile, update_profile, list_all_tasks, state_task_summary, statewise_summary,state_dashboard_summary

)

urlpatterns = [
    # ✅ Dashboard
    path('api/dashboard/', superadmin_dashboard_api, name='superadmin-dashboard-api'),

    # ✅ Admin management
    path('api/admins/', manage_admins, name='superadmin-admin-list-create'),
    path('api/admins/<int:admin_id>/', update_delete_admin, name='superadmin-admin-update-delete'),

    # ✅ Employee management
    path('api/employees/', manage_employees, name='superadmin-employee-list-create'),
    path('api/employees/<int:employee_id>/', update_delete_employee, name='superadmin-employee-update-delete'),

    # ✅ Report moderation
    path('api/reports/', list_reports, name='superadmin-reports'),
    path('api/reports/<int:report_id>/approve/', approve_report, name='superadmin-report-approve'),
    path('api/reports/<int:report_id>/reject/', reject_report, name='superadmin-report-reject'),

    # ✅ Conflict resolution
    path('api/conflicts/', list_conflicts, name='superadmin-conflict-list'),
    path('api/conflicts/<int:conflict_id>/resolve/', resolve_conflict, name='superadmin-conflict-resolve'),

    # ✅ SuperAdmin profile
    path('api/profile/', view_profile, name='superadmin-profile-view'),
    path('api/profile/update/', update_profile, name='superadmin-profile-update'),

    path('api/tasks/', list_all_tasks, name='superadmin-tasks'),
    path('api/summary/statewise/', statewise_summary, name='superadmin-statewise-summary'),

    path('state-task-summary/', state_task_summary),
    path('state-dashboard-summary/', state_dashboard_summary),
    
]
