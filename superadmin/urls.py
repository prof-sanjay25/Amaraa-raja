from django.urls import path
from . import views

urlpatterns = [
    # ----------------------------
    # Site Data Management
    # ----------------------------
    path("site-data-list/", views.site_data_list, name="site-data-list"),
    path("import-site-data/", views.import_site_data, name="import-site-data"),
    path("export-site-data/", views.export_site_data, name="export-site-data"),

    # ----------------------------
    # Form Management
    # ----------------------------
    path("get-form-by-task-type/", views.get_form_by_task_type, name="get-form-by-task-type"),
    path("get-task-type-mappings/", views.get_task_type_mappings, name="get-task-type-mappings"),

    path("import-dg-pm-cm-form/", views.import_dg_pm_cm_form, name="import-dg-pm-cm-form"),
    path("export-dg-pm-cm-form/", views.export_dg_pm_cm_form, name="export-dg-pm-cm-form"),
    path("get-dg-pm-cm-form/", views.get_dg_pm_cm_form, name="get-dg-pm-cm-form"),

    path("import-ac-pm-cm-form/", views.import_ac_pm_cm_form, name="import-ac-pm-cm-form"),
    path("export-ac-pm-cm-form/", views.export_ac_pm_cm_form, name="export-ac-pm-cm-form"),
    path("get-ac-pm-cm-form/", views.get_ac_pm_cm_form, name="get-ac-pm-cm-form"),

    path("import-site-visit-form/", views.import_site_visit_form, name="import-site-visit-form"),
    path("export-site-visit-form/", views.export_site_visit_form, name="export-site-visit-form"),
    path("get-site-visit-form/", views.get_site_visit_form, name="get-site-visit-form"),

    # ----------------------------
    # Admin Management
    # ----------------------------
    path("admins/", views.list_admins, name="list-admins"),
    path("admins/create/", views.create_admin, name="create-admin"),
    path("admins/bulk-create/", views.bulk_create_admins_zip, name="bulk-create-admins"),
    path("admins/<int:id>/", views.get_admin, name="get-admin"),
    path("admins/<int:id>/update/", views.update_admin, name="update-admin"),
    path("admins/<int:id>/delete/", views.delete_admin, name="delete-admin"),
    path("admins/<int:id>/toggle-status/", views.toggle_admin_status, name="toggle-admin-status"),
    path("admins/export/", views.export_admins_csv, name="export-admins-csv"),
    path("superadmins/", views.list_superadmins, name="list_superadmins"),

    path("admins/sample-zip/", views.download_sample_admins_zip, name="sample-admins-zip"),


    # ----------------------------
    # Employee Management
    # ----------------------------
    path("employees/", views.list_employees, name="list-employees"),
    path("employees/create/", views.create_employee, name="create-employee"),
    path("employees/bulk-create/", views.bulk_create_employees_zip, name="bulk-create-employees"),
    path("employees/sample-zip/", views.bulk_employee_sample_zip, name="sample-employees-zip"),  # ✅ NEW
    path("employees/<int:id>/", views.get_employee, name="get-employee"),
    path("employees/<int:id>/update/", views.update_employee, name="update-employee"),
    path("employees/<int:id>/delete/", views.delete_employee, name="delete-employee"),
    path("employees/<int:id>/toggle-status/", views.toggle_employee_status, name="toggle-employee-status"),
    path("employees/export/", views.export_employees_csv, name="export-employees-csv"),

    # ----------------------------
    # Task & Report Management (Superadmin)
    # ----------------------------  
    path("tasks/", views.list_tasks, name="list-tasks"),
    path("tasks/<str:task_id>/delete/", views.delete_task, name="delete-task"),

    # Bulk Export
    path("tasks/export/csv/", views.export_tasks_csv, name="export-tasks-csv"),
    path("tasks/export/pdf/", views.export_tasks_pdf, name="export-tasks-pdf"),

    # Reports
    path("reports/", views.list_reports, name="list-reports"),
    path("report/<int:report_id>/", views.view_report, name="view-report"),
    path("report-review/", views.review_report, name="review-report"),

    # Single report export
    path("report/<int:report_id>/export/csv/", views.export_report_csv, name="export-report-csv"),
    path("report/<int:report_id>/export/pdf/", views.export_report_pdf, name="export-report-pdf"),

    # ----------------------------
    # Audit Logs
    # ----------------------------
    path("audit-logs/", views.list_audit_logs, name="list-audit-logs"),

    # ----------------------------
    # Dashboard (Production)
    # ----------------------------
    # Legacy (optional) — remove if not needed
    # path("dashboard/", views.superadmin_dashboard, name="superadmin-dashboard"),

    # Main analytics endpoints
    path("dashboard/analytics/", views.dashboard_analytics, name="dashboard-analytics"),
    path("dashboard/export/", views.dashboard_export, name="dashboard-export"),
    path("dashboard/task-categories/", views.get_task_categories, name="get-task-categories"),
    path("dashboard/filter-options/", views.get_filter_options, name="get-filter-options"),

    
    path("profile/", views.superadmin_profile, name="superadmin-profile"),
    path('change-password/', views.change_password, name='change-password'),
]
