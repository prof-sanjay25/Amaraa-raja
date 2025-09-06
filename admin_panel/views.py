from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from django.http import HttpResponse
from django.core.files.storage import default_storage
from django.contrib.auth import get_user_model

from .models import Task, TaskType, Cluster, SiteData
from reports.models import Report
from .serializers import DashboardStatsSerializer

from django.template.loader import render_to_string
from weasyprint import HTML
import tempfile
import csv

User = get_user_model()

# --- 1. Dashboard Endpoint ---
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dashboard_stats(request):
    employees = User.objects.filter(role='employee')

    # List of task names to track, as you want on the cards
    TASK_TITLES = [
        "DG PM",
        "DG CM",
        "AC PM",
        "AC CM",
        "Site Visit",
    ]

    task_type_stats = []
    for name in TASK_TITLES:
        # Count by title (case-sensitive by default, you can add __iexact if you want case-insensitive)
        total = Task.objects.filter(title=name).count()
        completed = Task.objects.filter(title=name, status='completed').count()
        pending = Task.objects.filter(title=name, status='pending').count()
        in_progress = Task.objects.filter(title=name, status='in_progress').count()
        color = "#1976D2"  # you can map a color if you want, or just leave as default
        task_type_stats.append({
            'task_name': name,
            'total': total,
            'completed': completed,
            'pending': pending,
            'in_progress': in_progress,
            'color': color
        })

    stats = {
        'total_employees': employees.count(),
        'total_tasks': Task.objects.count(),
        'completed_tasks': Task.objects.filter(status='completed').count(),
        'pending_tasks': Task.objects.filter(status='pending').count(),
        'in_progress_tasks': Task.objects.filter(status='in_progress').count(),

        'task_type_stats': task_type_stats,

        'clusters': [
            {
                'name': cluster.name,
                'total': Task.objects.filter(cluster=cluster).count(),
                'completed': Task.objects.filter(cluster=cluster, status='completed').count(),
            }
            for cluster in Cluster.objects.all()
        ],

        'recent_assigned_tasks': [
            {
                'employee_id': t.assigned_to.id,
                'employee_name': t.assigned_to.first_name,
                'task_id': t.task_id,
                'task_type': t.type.name if t.type else '',
                'global_id': t.global_id
            }
            for t in Task.objects.select_related('assigned_to', 'type').order_by('-created_at')[:5]
        ],

        'recent_employees': [
            {
                'id': e.id,
                'name': e.first_name,
                'email': e.email,
                'designation': getattr(e, 'designation', ''),
                'global_id': getattr(e, 'global_id', ''),
                'state_user_id': getattr(e, 'state_user_id', ''),
                'state': getattr(e, 'state', ''),
                'active': e.is_active,
                'date_joined': e.date_joined,
            }
            for e in employees.order_by('-date_joined')[:5]
        ]
    }
    serializer = DashboardStatsSerializer(stats)
    return Response(serializer.data)




@api_view(['POST'])
@permission_classes([IsAuthenticated])
def assign_task(request):
    global_id = request.data.get('global_id')
    employee_email = request.data.get('employee_email')   # 🔹 now email only
    task_name = request.data.get('task_name')
    task_type_name = request.data.get('task_type')
    deadline = request.data.get('deadline')
    planned_date = request.data.get('planned_date')

    if not all([global_id, employee_email, task_name, task_type_name]):
        return Response({'error': 'Missing fields'}, status=400)

    try:
        site = SiteData.objects.get(global_id=global_id)
    except SiteData.DoesNotExist:
        return Response({'error': 'Invalid Global ID'}, status=400)

    try:
        employee = User.objects.get(email=employee_email, role='employee')
    except User.DoesNotExist:
        return Response({'error': 'Invalid employee_email'}, status=400)

    task_type, _ = TaskType.objects.get_or_create(
        name=task_type_name,
        defaults={'color_code': '#888888'}
    )
    cluster, _ = Cluster.objects.get_or_create(name=site.cluster_name)

    admin_user = request.user

    task = Task.objects.create(
        
        global_id=global_id,
        title=task_name,
        description='',
        status='pending',
        type=task_type,
        cluster=cluster,
        assigned_to=employee,
        deadline=deadline,
        planned_date=planned_date,
        site=site,
        site_name=site.site_name,
        cluster_name=site.cluster_name,
        assigned_by=admin_user
    )

    return Response({
        'message': 'Task assigned',
        'task_id': task.task_id,
        'employee_email': employee.email,   # 🔹 consistent with bulk
        'planned_date': planned_date
    })



import datetime
import csv, io
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from admin_panel.models import Task, TaskType, SiteData, Cluster

@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser])
@permission_classes([IsAuthenticated])
def bulk_assign_task_csv(request):
    """
    Bulk assign tasks from a CSV/TSV file.
    Expected headers (case-insensitive): 
    employee_email, task_name, task_type, global_id, planned_date
    """

    if 'file' not in request.FILES:
        return Response({'error': 'CSV file is required'}, status=400)

    file = request.FILES['file']
    decoded_file = file.read().decode('utf-8-sig')  # 🔹 handles BOM too

    # 🔹 Detect delimiter (comma vs tab)
    if "\t" in decoded_file and "," not in decoded_file:
        delimiter = "\t"
    else:
        delimiter = ","

    reader = csv.DictReader(io.StringIO(decoded_file), delimiter=delimiter)

    # 🔹 Ensure headers exist
    if not reader.fieldnames:
        return Response({'error': 'CSV file has no headers'}, status=400)

    # 🔹 Clean headers (strip + lowercase)
    reader.fieldnames = [h.strip().lower() for h in reader.fieldnames if h]

    # 🔹 Validate required headers
    required_headers = {"employee_email", "task_name", "task_type", "global_id", "planned_date"}
    missing = required_headers - set(reader.fieldnames)
    if missing:
        return Response({'error': f'Missing required headers: {", ".join(missing)}'}, status=400)

    results = []
    admin_user = request.user

    for idx, row in enumerate(reader, start=1):
        # 🔹 Clean each row (strip spaces)
        row = {k.strip().lower(): (v.strip() if v else "") for k, v in row.items()}

        employee_email = row.get('employee_email')
        task_name = row.get('task_name')
        task_type_name = row.get('task_type')
        global_id = row.get('global_id')
        planned_date_str = row.get('planned_date')

        # Validate required fields
        if not all([employee_email, task_name, task_type_name, global_id, planned_date_str]):
            results.append({'row': idx, 'error': 'Missing required fields', 'data': row})
            continue

        # Parse planned_date (accept DD-MM-YY and YYYY-MM-DD)
        planned_date = None
        for fmt in ("%d-%m-%y", "%Y-%m-%d"):
            try:
                planned_date = datetime.datetime.strptime(planned_date_str, fmt).date()

                break
            except ValueError:
                continue
        if not planned_date:
            results.append({'row': idx, 'error': f'Invalid planned_date format: {planned_date_str}', 'data': row})
            continue

        # Validate site
        try:
            site = SiteData.objects.get(global_id=global_id)
        except SiteData.DoesNotExist:
            results.append({'row': idx, 'error': 'Invalid Global ID', 'data': row})
            continue

        # Validate employee
        try:
            employee = User.objects.get(email=employee_email, role='employee')
        except User.DoesNotExist:
            results.append({'row': idx, 'error': 'Invalid employee_email', 'data': row})
            continue

        # Task type
        task_type, _ = TaskType.objects.get_or_create(
            name=task_type_name,
            defaults={'color_code': '#888888'}
        )

        # Cluster
        cluster, _ = Cluster.objects.get_or_create(name=site.cluster_name)

        # Create task (task_id auto-generated by signal)
        task = Task.objects.create(
            global_id=global_id,
            title=task_name,
            status='pending',
            type=task_type,
            cluster=cluster,
            assigned_to=employee,
            planned_date=planned_date,
            site=site,
            site_name=site.site_name,
            cluster_name=site.cluster_name,
            assigned_by=admin_user,
        )

        results.append({
            'row': idx,
            'message': 'Task assigned',
            'task_id': task.task_id,
            'employee_email': employee.email,
            'planned_date': str(planned_date)
        })

    if not results or all('error' in r for r in results):
        return Response({'results': results, 'message': 'No tasks created'}, status=400)

    return Response({'results': results, 'delimiter_used': delimiter}, status=200)









@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_tasks(request):
    status = request.GET.get('status')
    queryset = Task.objects.select_related(
        'assigned_to', 'type', 'cluster', 'assigned_by', 'site'
    ).order_by('-created_at')
    
    if status:
        queryset = queryset.filter(status=status)
    
    data = []
    for t in queryset:
        if getattr(t, 'site_name', None):
            resolved_site_name = t.site_name
        elif getattr(t, 'site', None):
            resolved_site_name = t.site.site_name
        else:
            resolved_site_name = ''

        data.append({
            'task_id': t.task_id,
            'global_id': t.global_id,
            'task_name': t.title,
            'task_type': t.type.name if t.type else '',
            'status': t.status,
            'assigned_date': t.created_at,
            'deadline': t.deadline,
            'planned_date': t.planned_date,   # 🔹 Added field
            'cluster_name': t.cluster.name if t.cluster else '',
            'site_name': resolved_site_name,
            'employee_id': t.assigned_to.id if t.assigned_to else None,
            'employee_name': t.assigned_to.first_name if t.assigned_to else '',
            'employee_email': t.assigned_to.email if t.assigned_to else '',
            'employee_global_id': getattr(t.assigned_to, 'global_id', '') if t.assigned_to else '',
            'employee_state_user_id': getattr(t.assigned_to, 'state_user_id', '') if t.assigned_to else '',
            'employee_state': getattr(t.assigned_to, 'state', '') if t.assigned_to else '',
            'assigned_by_id': t.assigned_by.id if t.assigned_by else None,
            'assigned_by_name': t.assigned_by.first_name if t.assigned_by else '',
            'assigned_by_email': t.assigned_by.email if t.assigned_by else '',

            # 🔹 Add reports here
            'reports': [
                {
                    'report_id': r.id,
                    'status': r.status,
                    'submitted_at': r.submitted_at,
                    'approved_at': r.approved_at,
                    'rejection_reason': r.rejection_reason,
                    'employee_name': t.assigned_to.first_name if t.assigned_to else "",
                    'employee_email': t.assigned_to.email if t.assigned_to else "",
                }
                for r in t.reports.all()
            ]


        
        })
    
    return Response(data)



@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_task(request, task_id):
    try:
        task = Task.objects.get(task_id=task_id)
        task.delete()
        return Response({'message': 'Task deleted'})
    except Task.DoesNotExist:
        return Response({'error': 'Task not found'}, status=404)

# --- 3. Import/Export Site Data ---
import logging
logger = logging.getLogger(__name__)

import os
from django.conf import settings

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def import_site_data(request):
    file = request.FILES.get('file')
    if not file:
        return Response({'error': 'No file provided'}, status=400)

    # Save file to media/site_data.csv
    # Ensure MEDIA_ROOT exists
    media_root = getattr(settings, 'MEDIA_ROOT', 'media')
    os.makedirs(media_root, exist_ok=True)
    saved_path = os.path.join(media_root, 'site_data.csv')
    with open(saved_path, 'wb+') as destination:
        for chunk in file.chunks():
            destination.write(chunk)

    # Parse the uploaded file
    raw = open(saved_path, 'rb').read()
    try:
        decoded = raw.decode('utf-8-sig').splitlines()
    except UnicodeDecodeError:
        try:
            decoded = raw.decode('latin1').splitlines()
        except UnicodeDecodeError:
            return Response({'error': 'Unable to decode file. Please save as UTF-8 or CSV again.'}, status=400)

    reader = csv.DictReader(decoded)

    # Remove old data before saving new
    SiteData.objects.all().delete()
    for row in reader:
        SiteData.objects.create(
            global_id=row['global_id'],
            cluster_name=row['cluster_name'],
            site_name=row['site_name'],
            latitude=row.get('latitude', ''),
            longitude=row.get('longitude', ''),
        )
    return Response({'message': 'Site data imported and stored (old data replaced)'})



@api_view(['GET'])
@permission_classes([IsAuthenticated])
def export_site_data(request):
    media_root = getattr(settings, 'MEDIA_ROOT', 'media')
    saved_path = os.path.join(media_root, 'site_data.csv')
    if not os.path.exists(saved_path):
        return Response({'error': 'No site data file found.'}, status=404)
    with open(saved_path, 'rb') as f:
        response = HttpResponse(f.read(), content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="site_data.csv"'
        return response



# --- 4. Report Management ---
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_reports(request):
    reports = Report.objects.select_related('task', 'submitted_by')
    data = []
    for r in reports:
        data.append({
            'report_id': r.id,
            'task_id': r.task.task_id,
            'global_id': r.task.global_id,
            'site_name': getattr(r.task, 'site_name', ''),
            'cluster_name': r.task.cluster.name if r.task.cluster else '',
            'employee_id': r.submitted_by.id,
            'employee_name': r.submitted_by.first_name,
            'employee_email': r.submitted_by.email,
            'employee_global_id': getattr(r.submitted_by, 'global_id', ''),
            'employee_state_user_id': getattr(r.submitted_by, 'state_user_id', ''),
            'employee_state': getattr(r.submitted_by, 'state', ''),
            'assigned_date': r.task.created_at,
            'submitted_date': r.submitted_at,
            'admin_name': r.task.assigned_by.first_name if r.task.assigned_by else '',
            'admin_email': r.task.assigned_by.email if r.task.assigned_by else '',
            'status': r.status,
        })
    return Response(data)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def review_report(request):
    report_id = request.data.get('report_id')
    action = request.data.get('action')
    reason = request.data.get('reason', '')

    try:
        report = Report.objects.select_related('task').get(id=report_id)
        if action == 'approve':
            report.status = 'approved'
            report.approved_at = timezone.now()
            report.task.status = 'completed'
            report.task.save()
        elif action == 'reject':
            report.status = 'rejected'
            report.rejection_reason = reason
            report.task.status = 'in_progress'  # Explicitly set back to in_progress
            report.task.save()
        else:
            return Response({'error': 'Invalid action'}, status=400)
        report.save()
        return Response({'message': f'Report {action}d'})
    except Report.DoesNotExist:
        return Response({'error': 'Report not found'}, status=404)



# --- 5. Employee Management ---

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.contrib.auth import get_user_model
from employees.models import Employee
from django.core.exceptions import ValidationError

User = get_user_model()

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_employee(request):
    admin = request.user

    # Required fields
    name = request.data.get('name')
    email = request.data.get('email')
    password = request.data.get('password')
    confirm_password = request.data.get('confirm_password')

    # Optional fields
    company_name = request.data.get('company_name')
    employee_id = request.data.get('employee_id')
    mobile_number = request.data.get('mobile_number')
    manager_id = request.data.get('manager_id')

    passport_photo = request.FILES.get('passport_photo')
    signature_photo = request.FILES.get('signature_photo')

    # Validation
    if not all([name, email, password, confirm_password]):
        return Response({'error': 'Missing required fields (name, email, password, confirm_password)'}, status=400)

    if password != confirm_password:
        return Response({'error': 'Passwords do not match'}, status=400)

    try:
        User.validate_password_strength(password)
    except ValidationError as e:
        return Response({'error': str(e)}, status=400)

    if User.objects.filter(email=email).exists():
        return Response({'error': 'Email already exists'}, status=400)

    # Create user
    user = User.objects.create_user(
        username=name,
        email=email,
        password=password,
        first_name=name,
        state=admin.state,
        role='employee',
        is_active=True
    )

    # Find manager if provided
    manager = None
    if manager_id:
        try:
            manager = User.objects.get(id=manager_id)
        except User.DoesNotExist:
            return Response({'error': 'Manager not found'}, status=404)

    # Create Employee profile
    employee = Employee.objects.create(
        user=user,
        company_name=company_name,
        employee_id=employee_id,
        mobile_number=mobile_number,
        passport_photo=passport_photo,
        signature_photo=signature_photo,
        manager=manager
    )

    return Response({
        'message': 'Employee created',
        'user_id': user.id,
        'global_id': user.global_id,
        'state_user_id': user.state_user_id,
        'employee_id': employee.employee_id
    })


import zipfile, tempfile, os, csv
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from employees.models import Employee

User = get_user_model()


def find_photo_anywhere(temp_dir, email, kind):
    """
    Search recursively for photo files by email and type (passport/signature).
    Works with or without extensions (.jpg/.jpeg/.png) and case-insensitive.
    """
    base_name = f"{email.lower()}_{kind}"
    for root, dirs, files in os.walk(temp_dir):
        for f in files:
            name, ext = os.path.splitext(f.lower())
            if name == base_name:  # ✅ match even without extension
                return os.path.join(root, f)
            if f.lower().startswith(base_name):  # ✅ catch base + extension
                if ext in ["", ".jpg", ".jpeg", ".png"]:
                    return os.path.join(root, f)
    return None



@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser])
@permission_classes([IsAuthenticated])
def bulk_create_employees_zip(request):
    """
    Bulk create employees from a ZIP file containing employees.csv + photos/.
    Photos must be named: <email>_passport(.jpg/.jpeg/.png) and <email>_signature(.jpg/.jpeg/.png)
    or without extension.
    """
    if 'file' not in request.FILES:
        return Response({'error': 'ZIP file is required'}, status=400)

    zip_file = request.FILES['file']
    temp_dir = tempfile.mkdtemp()

    with zipfile.ZipFile(zip_file, 'r') as z:
        z.extractall(temp_dir)

    # 🔹 Find employees.csv
    csv_path = None
    for root, dirs, files in os.walk(temp_dir):
        if "employees.csv" in [f.lower() for f in files]:
            # normalize case-insensitive
            for f in files:
                if f.lower() == "employees.csv":
                    csv_path = os.path.join(root, f)
                    break
            break

    if not csv_path:
        return Response({'error': 'employees.csv not found in ZIP'}, status=400)

    results = []
    admin = request.user

    with open(csv_path, newline='', encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        reader.fieldnames = [h.strip().lower() for h in reader.fieldnames if h]

        for idx, row in enumerate(reader, start=1):
            name = row.get('name')
            email = row.get('email')
            password = row.get('password')
            confirm_password = row.get('confirm_password')
            company_name = row.get('company_name')
            employee_id = row.get('employee_id')
            mobile_number = row.get('mobile_number')

            # --- Validation ---
            if not all([name, email, password, confirm_password]):
                results.append({'row': idx, 'error': 'Missing required fields'})
                continue
            if password != confirm_password:
                results.append({'row': idx, 'error': 'Passwords do not match'})
                continue
            if User.objects.filter(email=email).exists():
                results.append({'row': idx, 'error': 'Email already exists'})
                continue
            try:
                User.validate_password_strength(password)
            except ValidationError as e:
                results.append({'row': idx, 'error': str(e)})
                continue

            # --- Create User ---
            user = User.objects.create_user(
                username=name,
                email=email,
                password=password,
                first_name=name,
                state=admin.state,
                role='employee',
                is_active=True
            )

            # --- Find photos ---
            passport_path = find_photo_anywhere(temp_dir, email, "passport")
            signature_path = find_photo_anywhere(temp_dir, email, "signature")

            passport_file = None
            signature_file = None
            warnings = []

            if passport_path:
                with open(passport_path, "rb") as pf:
                    passport_file = SimpleUploadedFile(
                        name=os.path.basename(passport_path),
                        content=pf.read(),
                        content_type="image/jpeg"
                    )
            else:
                warnings.append("Passport photo missing")

            if signature_path:
                with open(signature_path, "rb") as sf:
                    signature_file = SimpleUploadedFile(
                        name=os.path.basename(signature_path),
                        content=sf.read(),
                        content_type="image/jpeg"
                    )
            else:
                warnings.append("Signature photo missing")

            # --- Create Employee profile ---
            employee = Employee.objects.create(
                user=user,
                company_name=company_name,
                employee_id=employee_id,
                mobile_number=mobile_number,
                passport_photo=passport_file,
                signature_photo=signature_file,
            )

            results.append({
                'row': idx,
                'message': 'Employee created',
                'email': email,
                'user_id': user.id,
                'employee_id': employee.employee_id,
                'passport_photo_saved': bool(passport_file),
                'signature_photo_saved': bool(signature_file),
                'warnings': warnings,
            })

    return Response({'results': results})







# --- 5. Employee Management ---

from django.shortcuts import get_object_or_404

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def toggle_employee_status(request, id):
    employee = get_object_or_404(User, id=id, role='employee')
    action = request.data.get('action')  # 'suspend' or 'activate'

    if action == 'suspend':
        employee.is_active = False
    elif action == 'activate':
        employee.is_active = True
    else:
        return Response({'status': 'error', 'message': 'Invalid action specified'}, status=400)

    employee.save()
    profile = getattr(employee, 'employee_profile', None)

    return Response({
        'status': 'success',
        'employee': {
            'id': employee.id,
            'name': employee.first_name,
            'email': employee.email,
            'company_name': profile.company_name if profile else '',
            'employee_id': profile.employee_id if profile else '',
            'mobile_number': profile.mobile_number if profile else '',
            'global_id': employee.global_id,
            'state_user_id': employee.state_user_id,
            'state': employee.state,
            'is_active': employee.is_active,
            'date_joined': employee.date_joined,
        }
    })


from django.conf import settings

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_employees(request):
    employees = User.objects.filter(role='employee')
    data = []
    for e in employees:
        profile = getattr(e, 'employee_profile', None)

        # Build full URLs for media files
        def build_url(file_field):
            if file_field and hasattr(file_field, 'url'):
                return request.build_absolute_uri(file_field.url)
            return None

        data.append({
            'id': e.id,
            'name': e.first_name,
            'email': e.email,
            'company_name': profile.company_name if profile else '',
            'employee_id': profile.employee_id if profile else '',
            'mobile_number': profile.mobile_number if profile else '',
            'passport_photo': build_url(profile.passport_photo) if profile else None,
            'signature_photo': build_url(profile.signature_photo) if profile else None,
            'global_id': e.global_id,
            'state_user_id': e.state_user_id,
            'state': e.state,
            'is_active': e.is_active,
            'date_joined': e.date_joined,
        })
    return Response(data)


from django.shortcuts import get_object_or_404

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_employee(request, id):
    employee = get_object_or_404(User, id=id, role='employee')
    profile = getattr(employee, 'employee_profile', None)

    def build_url(file_field):
        if file_field and hasattr(file_field, 'url'):
            return request.build_absolute_uri(file_field.url)
        return None

    data = {
        'id': employee.id,
        'name': employee.first_name,
        'email': employee.email,
        'company_name': profile.company_name if profile else '',
        'employee_id': profile.employee_id if profile else '',
        'mobile_number': profile.mobile_number if profile else '',
        'passport_photo': build_url(profile.passport_photo) if profile else None,
        'signature_photo': build_url(profile.signature_photo) if profile else None,
        'global_id': employee.global_id,
        'state_user_id': employee.state_user_id,
        'state': employee.state,
        'is_active': employee.is_active,
        'date_joined': employee.date_joined,
    }
    return Response(data)



@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def update_employee(request, id):
    employee = get_object_or_404(User, id=id, role='employee')
    profile, _ = Employee.objects.get_or_create(user=employee)

    # Update user fields
    employee.first_name = request.data.get('name', employee.first_name)
    employee.email = request.data.get('email', employee.email)
    if 'is_active' in request.data:
        employee.is_active = request.data['is_active']
    if 'state' in request.data:
        employee.state = request.data['state']
    employee.save()

    # Update employee profile fields
    profile.company_name = request.data.get('company_name', profile.company_name)
    profile.employee_id = request.data.get('employee_id', profile.employee_id)
    profile.mobile_number = request.data.get('mobile_number', profile.mobile_number)

    if 'passport_photo' in request.FILES:
        profile.passport_photo = request.FILES['passport_photo']
    if 'signature_photo' in request.FILES:
        profile.signature_photo = request.FILES['signature_photo']

    profile.save()

    return Response({'message': 'Employee updated'})


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_employee(request, id):
    try:
        user = User.objects.get(id=id, role='employee')
        user.delete()
        return Response({'message': 'Employee deleted'})
    except User.DoesNotExist:
        return Response({'error': 'Employee not found'}, status=404)


import datetime

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def export_employees_csv(request):
    employees = User.objects.filter(role='employee')

    # 🔹 Always generate unique filename with timestamp
    now = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"employee_details_{now}.csv"

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename={filename}'

    writer = csv.writer(response)

    writer.writerow([
        'Name',
        'Email',
        'Company Name',
        'Employee ID',
        'Mobile Number',
        'State',
        'Is Active',
        'Date Joined',
        'Passport Photo',
        'Signature Photo',
    ])

    for e in employees:
        profile = getattr(e, 'employee_profile', None)

        def build_url(file_field):
            if file_field and hasattr(file_field, 'url'):
                return request.build_absolute_uri(file_field.url)
            return ''

        writer.writerow([
            e.first_name,
            e.email,
            profile.company_name if profile else '',
            profile.employee_id if profile else '',
            profile.mobile_number if profile else '',
            e.state,
            'Active' if e.is_active else 'Suspended',
            e.date_joined.strftime("%Y-%m-%d %H:%M:%S"),
            build_url(profile.passport_photo) if profile else '',
            build_url(profile.signature_photo) if profile else '',
        ])

    return response


import pandas as pd
import io
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from forms.models import FormTemplate

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser])
def import_dg_pm_cm_form(request):
    """
    Upload a new DG PM/CM form template (CSV or XLSX).
    Completely replaces any previous DG PM/CM fields in FormTemplate.
    Accepts CSV or Excel with columns: label, field_type, required, options, order, [key]
    """
    file = request.FILES.get('file')
    if not file:
        return Response({'error': 'No file provided'}, status=400)

    filename = file.name.lower()
    schema = []

    try:
        if filename.endswith('.csv'):
            df = pd.read_csv(file)
        elif filename.endswith('.xlsx'):
            df = pd.read_excel(file)
        else:
            return Response({'error': 'Unsupported file format. Please upload a .csv or .xlsx file.'}, status=400)

        # Normalize column names
        df.columns = [c.strip().lower() for c in df.columns]
        for _, row in df.iterrows():
            schema.append({
                'label': str(row['label']).strip(),
                'field_type': str(row['field_type']).strip(),
                'required': str(row.get('required', '')).strip().lower() == 'true',
                'options': [opt.strip() for opt in str(row.get('options', '')).split(',') if opt.strip()],
                'order': int(row.get('order', 0)) if str(row.get('order', '0')).isdigit() else 0,
                'key': str(row.get('key', str(row['label']).strip().lower().replace(' ', '_'))),
            })
    except Exception as e:
        return Response({'error': f'Failed to parse file: {e}'}, status=400)

    # Remove the old schema and save new one
    FormTemplate.objects.filter(task_group='dg').delete()
    FormTemplate.objects.create(
        task_group='dg',
        schema=schema
    )

    return Response({'message': 'DG PM/CM form uploaded (old fields replaced)', 'fields': len(schema)})



@api_view(['GET'])
@permission_classes([IsAuthenticated])
def export_dg_pm_cm_form(request):
    path = default_storage.path('dg_pm_cm_questions.xlsx')
    with open(path, 'rb') as f:
        response = HttpResponse(f.read(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = 'attachment; filename="DG_PM_CM_Questions.xlsx"'
        return response

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def import_ac_pm_cm_form(request):
    file = request.FILES.get('file')
    if not file:
        return Response({'error': 'No file provided'}, status=400)
    path = default_storage.save('ac_pm_cm_questions.xlsx', file)
    return Response({'message': 'AC PM/CM question fields imported'})

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def export_ac_pm_cm_form(request):
    path = default_storage.path('ac_pm_cm_questions.xlsx')
    with open(path, 'rb') as f:
        response = HttpResponse(f.read(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = 'attachment; filename="AC_PM_CM_Questions.xlsx"'
        return response

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def import_site_visit_form(request):
    file = request.FILES.get('file')
    if not file:
        return Response({'error': 'No file provided'}, status=400)
    path = default_storage.save('site_visit_questions.xlsx', file)
    return Response({'message': 'Site Visit question fields imported'})

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def export_site_visit_form(request):
    path = default_storage.path('site_visit_questions.xlsx')
    with open(path, 'rb') as f:
        response = HttpResponse(f.read(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = 'attachment; filename="Site_Visit_Questions.xlsx"'
        return response

# --- Admin Profile ---
@api_view(['GET', 'PUT'])
@permission_classes([IsAuthenticated])
def admin_profile(request):
    admin = request.user
    if request.method == 'GET':
        data = {
            'id': admin.id,
            'fullName': admin.first_name if hasattr(admin, 'first_name') else admin.username,
            'email': admin.email,
            'role': admin.role,
            'global_id': getattr(admin, 'global_id', ''),
            'state_user_id': getattr(admin, 'state_user_id', ''),
            'state': getattr(admin, 'state', ''),
            'is_active': admin.is_active,
            'date_joined': admin.date_joined,
        }
        return Response(data)
    elif request.method == 'PUT':
        name = request.data.get('fullName')
        if name:
            admin.first_name = name
            admin.save()
        return Response({'message': 'Profile updated'})

# --- View Report ---
from django.utils.dateformat import format

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def view_report(request, report_id):
    try:
        report = Report.objects.select_related('task', 'submitted_by', 'task__assigned_to').get(id=report_id)
    except Report.DoesNotExist:
        return Response({'error': 'Report not found'}, status=404)

    form_data = []
    if hasattr(report, 'data') and isinstance(report.data, dict):
        for key, value in report.data.items():
            form_data.append({'label': key, 'answer': value})

    files = []
    if hasattr(report, 'files'):
        files = [
            {'label': f.field_label, 'url': request.build_absolute_uri(f.file.url)}
            for f in report.files.all()
        ]

    data = {
        'report_id': report.id,
        'task_id': report.task.task_id,
        'global_id': report.task.global_id,
        'site_name': getattr(report.task, 'site_name', ''),
        'cluster_name': report.task.cluster.name if report.task.cluster else '',
        'employee_id': report.submitted_by.id,
        'employee_name': report.submitted_by.first_name,
        'employee_email': report.submitted_by.email,
        'employee_global_id': getattr(report.submitted_by, 'global_id', ''),
        'employee_state_user_id': getattr(report.submitted_by, 'state_user_id', ''),
        'employee_state': getattr(report.submitted_by, 'state', ''),
        'approved_at': report.approved_at.isoformat() if report.approved_at else None,
        'submitted_date': report.submitted_at.isoformat() if report.submitted_at else None,
        'assigned_date': report.task.created_at.isoformat() if report.task and report.task.created_at else None,
        'admin_name': report.task.assigned_by.first_name if report.task.assigned_by else '',
        'admin_email': report.task.assigned_by.email if report.task.assigned_by else '',
        'status': report.status,
        'form_data': form_data,
        'files': files,
    }
    return Response(data)

# --- Change Password ---
from django.core.exceptions import ValidationError

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def change_password(request):
    user = request.user
    old_password = request.data.get('old_password')
    new_password = request.data.get('new_password')
    confirm_password = request.data.get('confirm_password')

    # Validation
    if not all([old_password, new_password, confirm_password]):
        return Response({'error': 'Missing fields (old_password, new_password, confirm_password required)'}, status=400)

    if not user.check_password(old_password):
        return Response({'error': 'Old password is incorrect'}, status=400)

    if new_password != confirm_password:
        return Response({'error': 'Passwords do not match'}, status=400)

    try:
        User.validate_password_strength(new_password)
    except ValidationError as e:
        return Response({'error': str(e)}, status=400)

    # Set new password
    user.set_password(new_password)
    user.save()

    return Response({'message': 'Password changed successfully'})



# --- Site Data List ---
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def site_data_list(request):
    sites = SiteData.objects.all().order_by('cluster_name', 'site_name')
    data = [
        {
            'global_id': s.global_id,
            'cluster_name': s.cluster_name,
            'site_name': s.site_name,
            'latitude': s.latitude,
            'longitude': s.longitude,
        }
        for s in sites
    ]
    return Response(data)



import csv
import io
import json
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils.timezone import localtime
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from reports.models import Report
from weasyprint import HTML


# --- Helper: Safe datetime formatter ---
def format_datetime(dt):
    if not dt:
        return ''
    try:
        return localtime(dt).strftime("%d-%m-%Y %H:%M")
    except Exception:
        return str(dt)


# --- Export Report as PDF ---
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def export_report_pdf(request, report_id):
    """
    Generate a PDF for a report and return as HTTP response.
    """
    try:
        report = Report.objects.select_related(
            'task', 'submitted_by', 'task__assigned_to'
        ).prefetch_related('files').get(id=report_id)
    except Report.DoesNotExist:
        return Response({'error': 'Report not found'}, status=404)

    # 1. Parse form data
    raw_data = report.data
    form_data = {}

    if isinstance(raw_data, str):
        try:
            raw_data = json.loads(raw_data)
        except Exception:
            raw_data = {}

    def safe_section_key(s):
        return s.replace(" ", "_")

    if isinstance(raw_data, dict):
        is_sectioned = all(
            isinstance(v, list) and all(isinstance(item, dict) for item in v)
            for v in raw_data.values()
        )
        if is_sectioned:
            for section, rows in raw_data.items():
                form_data[safe_section_key(section)] = rows
        else:
            form_data['Main_Section'] = [{"label": k, "value": v} for k, v in raw_data.items()]
    elif isinstance(raw_data, list):
        form_data['Main_Section'] = [
            {"label": item.get("label", ""), "value": item.get("answer", item.get("value", ""))}
            for item in raw_data if isinstance(item, dict)
        ]
    else:
        form_data['Main_Section'] = [{"label": "Report Data", "value": str(raw_data)}]

    # Cleanup duplicate labels
    task_labels_to_remove = [
        "Global ID", "Site Name", "Cluster", "Service Engineer Name", "Service Type"
    ]
    if 'Main_Section' in form_data:
        form_data['Main_Section'] = [
            item for item in form_data['Main_Section']
            if item.get("label") not in task_labels_to_remove
        ]

    if "Main Section" in form_data:
        form_data["Main_Section"] = form_data.pop("Main Section")

    # Left and Right sections
    left_sections = ["Main_Section", "Engine_Details", "Engine_Check_Points", "Alternator_Check_Points"]
    right_sections = ["Alternator_Details", "General_Check_Points"]

    # Context for template
    context = {
        'report_title': f"Task Report - {getattr(getattr(report, 'task', None), 'type', None) and getattr(report.task.type, 'name', '')}",
        'task_type': getattr(getattr(report, "task", None), "type", None) and getattr(report.task.type, "name", ""),
        'task_id': getattr(report.task, "task_id", ""),
        'report_id': report.id,
        'global_id': getattr(report.task, "global_id", ""),
        'site_name': getattr(report.task, 'site_name', ''),
        'cluster_name': getattr(report.task, "cluster", None) and getattr(report.task.cluster, "name", ""),
        'assigned_by': getattr(report.task, "assigned_by", None) and getattr(report.task.assigned_by, "first_name", ""),
        'employee_name': getattr(report.submitted_by, "first_name", ""),
        'assigned_date': format_datetime(getattr(report.task, "created_at", "")),
        'submitted_at': format_datetime(getattr(report, "submitted_at", "")),
        'approved_at': format_datetime(getattr(report, "approved_at", "")),
        'status': getattr(report, "status", ""),
        'form_data': form_data,
        'files': [
            {'label': f.field_label, 'url': request.build_absolute_uri(f.file.url)}
            for f in getattr(report, "files", []).all()
        ] if hasattr(report, "files") else [],
        'state': getattr(getattr(report.task, "assigned_by", None), "state", "Andhra Pradesh"),
        'left_sections': left_sections,
        'right_sections': right_sections,
        'logo_url': "/static/images/company_logo.png",
    }

    # Render and export PDF
    html_string = render_to_string('report_pdf.html', context)
    pdf_file = io.BytesIO()
    HTML(string=html_string).write_pdf(pdf_file)
    pdf_file.seek(0)

    response = HttpResponse(pdf_file.read(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename=report_{report.id}.pdf'
    return response


# --- Export Report as CSV ---
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def export_report_csv(request, report_id):
    try:
        report = Report.objects.select_related(
            'task', 'submitted_by', 'task__assigned_to'
        ).prefetch_related('files').get(id=report_id)
    except Report.DoesNotExist:
        return Response({'error': 'Report not found'}, status=404)

    raw_data = report.data
    if isinstance(raw_data, str):
        try:
            raw_data = json.loads(raw_data)
        except Exception:
            raw_data = {}

    rows = []

    # Normalize form data
    if isinstance(raw_data, dict):
        for section, items in raw_data.items():
            for item in items:
                rows.append({
                    'section': section,
                    'label': item.get('label', ''),
                    'value': item.get('value', item.get('answer', ''))
                })
    elif isinstance(raw_data, list):
        for item in raw_data:
            rows.append({
                'section': 'Main Section',
                'label': item.get('label', ''),
                'value': item.get('value', item.get('answer', ''))
            })

    # Add metadata
    meta_info = [
        ('Report ID', report.id),
        ('Task ID', getattr(report.task, 'task_id', '')),
        ('Global ID', getattr(report.task, 'global_id', '')),
        ('Site Name', getattr(report.task, 'site_name', '')),
        ('Cluster Name', getattr(getattr(report.task, 'cluster', None), 'name', '')),
        ('Employee', getattr(report.submitted_by, 'first_name', '')),
        ('Submitted At', format_datetime(report.submitted_at)),
        ('Approved At', format_datetime(report.approved_at)),
        ('Status', report.status),
    ]
    rows = [{'section': 'Meta', 'label': k, 'value': v} for k, v in meta_info] + rows

    # Add uploaded files
    if hasattr(report, "files"):
        for f in report.files.all():
            rows.append({
                'section': 'Files',
                'label': f.field_label,
                'value': request.build_absolute_uri(f.file.url)
            })

    # Write CSV
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=['section', 'label', 'value'])
    writer.writeheader()
    for row in rows:
        writer.writerow(row)

    response = HttpResponse(buffer.getvalue(), content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename=report_{report.id}.csv'
    return response
