from django.urls import path
from . import views

urlpatterns = [
    # Dashboard
    path('dashboard/', views.dashboard_stats, name='dashboard-stats'),

    # Employee CRUD
    path('employees/', views.list_employees, name='list-employees'),
    path('employee/<int:id>/', views.get_employee, name='get-employee'),
    path('employee/<int:id>/update/', views.update_employee, name='update-employee'),
    path('employee/<int:id>/delete/', views.delete_employee, name='delete-employee'),
    path('employee/<int:id>/toggle-status/', views.toggle_employee_status, name='toggle-employee-status'),
    path('create-employee/', views.create_employee, name='create-employee'),
    path('bulk-create-employees-zip/', views.bulk_create_employees_zip, name='bulk-create-employees-zip'),
    path('employees/export/', views.export_employees_csv, name='export-employees-csv'),

    # ✅ NEW: Bulk Employee Sample ZIP (with manager_email)
    path('bulk-employee-sample-zip/', views.bulk_employee_sample_zip, name='bulk-employee-sample-zip'),



    path('admins/', views.list_admins, name='list-admins'),

    # Task Management
    path('suggest-global-ids/', views.suggest_global_ids, name='suggest-global-ids'),  # NEW
    path('assign-task/', views.assign_task, name='assign-task'),
    path('bulk-assign-csv/', views.bulk_assign_task_csv, name='bulk-assign-csv'),
    path('bulk-assign-csv-template/', views.bulk_assign_csv_template, name='bulk_assign_csv_template'),
    path('tasks/', views.list_tasks, name='list-tasks'),
    path('delete-task/<str:task_id>/', views.delete_task, name='delete-task'),

    # ✅ NEW: Bulk Task Export
    path('tasks/export/csv/', views.export_tasks_csv, name='bulk-export-csv'),
    path('tasks/export/pdf/', views.export_tasks_pdf, name='bulk-export-pdf'),

    # Report Management
    path('reports/', views.list_reports, name='list-reports'),
    path('report/<int:report_id>/', views.view_report, name='view-report'),
    path('report/<int:report_id>/export/pdf/', views.export_report_pdf, name='export-report-pdf'),
    path('report/<int:report_id>/export/csv/', views.export_report_csv, name='export-report-csv'),
    path('report-review/', views.review_report, name='review-report'),

    # Admin Profile & Security
    path('profile/', views.admin_profile, name='admin-profile'),
    path('change-password/', views.change_password, name='change-password'),

    # Audit & Compliance
    path('audit-logs/', views.list_audit_logs, name='list-audit-logs'),  # NEW

    # Commented sections can be uncommented when those views are implemented
    # Site Management Import/Export
    # path('import-site-data/', views.import_site_data, name='import-site-data'),
    # path('export-site-data/', views.export_site_data, name='export-site-data'),

    # Form Configuration Management
    # path('import-dg-pm-cm-form/', views.import_dg_pm_cm_form, name='import-dg-pm-cm-form'),
    # path('export-dg-pm-cm-form/', views.export_dg_pm_cm_form, name='export-dg-pm-cm-form'),
    # path('import-ac-pm-cm-form/', views.import_ac_pm_cm_form, name='import-ac-pm-cm-form'),
    # path('export-ac-pm-cm-form/', views.export_ac_pm_cm_form, name='export-ac-pm-cm-form'),
    # path('import-site-visit-form/', views.import_site_visit_form, name='import-site-visit-form'),
    # path('export-site-visit-form/', views.export_site_visit_form, name='export-site-visit-form'),

    # Form Retrieval
    # path('get-dg-pm-cm-form/', views.get_dg_pm_cm_form, name='get-dg-pm-cm-form'),
    # path('get-ac-pm-cm-form/', views.get_ac_pm_cm_form, name='get-ac-pm-cm-form'),
    # path('get-site-visit-form/', views.get_site_visit_form, name='get-site-visit-form'),
]