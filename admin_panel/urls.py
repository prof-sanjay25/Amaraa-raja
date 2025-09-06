from django.urls import path
from . import views

urlpatterns = [
    path('dashboard/', views.dashboard_stats, name='dashboard-stats'),

    # Employee CRUD
    path('employees/', views.list_employees, name='list-employees'),
    path('employee/<int:id>/', views.get_employee, name='get-employee'),
    path('employee/<int:id>/update/', views.update_employee, name='update-employee'),
    path('employee/<int:id>/delete/', views.delete_employee, name='delete-employee'),
    path('employee/<int:id>/toggle-status/', views.toggle_employee_status, name='toggle-employee-status'),
    path('create-employee/', views.create_employee, name='create-employee'),
    path('bulk-create-employees-zip/', views.bulk_create_employees_zip, name='bulk-create-employees-zip'),
    path('employees/export/', views.export_employees_csv, name='export_employees_csv'),

    # Tasks
    path('assign-task/', views.assign_task, name='assign-task'),
    path('bulk-assign-csv/', views.bulk_assign_task_csv, name='bulk-assign-csv'),
    path('tasks/', views.list_tasks, name='list-tasks'),
    path('delete-task/<str:task_id>/', views.delete_task, name='delete-task'),


 
    # Reports
    path('reports/', views.list_reports, name='list-reports'),
    path('report/<int:report_id>/', views.view_report, name='view-report'),
    path('report/<int:report_id>/export/pdf/', views.export_report_pdf, name='export-report-pdf'),
    path('report/<int:report_id>/export/csv/', views.export_report_csv, name='export-report-csv'),
    path('report-review/', views.review_report, name='review-report'),


    # Site Management Import/Export
    path('import-site-data/', views.import_site_data, name='import-site-data'),
    path('export-site-data/', views.export_site_data, name='export-site-data'),

    path('import-dg-pm-cm-form/', views.import_dg_pm_cm_form, name='import-dg-pm-cm-form'),
    path('export-dg-pm-cm-form/', views.export_dg_pm_cm_form, name='export-dg-pm-cm-form'),
    path('import-ac-pm-cm-form/', views.import_ac_pm_cm_form, name='import-ac-pm-cm-form'),
    path('export-ac-pm-cm-form/', views.export_ac_pm_cm_form, name='export-ac-pm-cm-form'),
    path('import-site-visit-form/', views.import_site_visit_form, name='import-site-visit-form'),
    path('export-site-visit-form/', views.export_site_visit_form, name='export-site-visit-form'),

    path('profile/', views.admin_profile, name='admin-profile'),
    
    path('change-password/', views.change_password, name='change-password'),
    path('site-data-list/', views.site_data_list, name='site-data-list'),


]
