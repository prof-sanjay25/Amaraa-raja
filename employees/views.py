from admin_panel.models import Task
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser
from reports.models import Report, ReportFileUpload





import json
import math
from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from admin_panel.models import Task
from reports.models import Report, ReportFileUpload
from admin_panel.models import SiteData   # 👈 make sure this matches your actual app name


def haversine(lat1, lon1, lat2, lon2):
    """Calculate distance in meters between two GPS points (Haversine formula)."""
    R = 6371000  # Radius of Earth in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def submit_report(request):
    user = request.user

    # Accept both multipart and JSON requests
    if hasattr(request, 'data') and hasattr(request.data, 'dict'):
        data = request.data.dict()
    else:
        data = request.data

    task_id = data.get('task_id') or request.POST.get('task_id')
    form_data_raw = data.get('form_data') or request.POST.get('form_data')
    user_lat = data.get('latitude') or request.POST.get('latitude')
    user_lon = data.get('longitude') or request.POST.get('longitude')

    if not task_id or not form_data_raw:
        return Response({'error': 'Missing task_id or form_data'}, status=400)

    # Parse form_data
    if isinstance(form_data_raw, dict):
        form_data = form_data_raw
    else:
        try:
            form_data = json.loads(form_data_raw)
        except Exception:
            form_data = {}

    # Get Task
    task = None
    try:
        task = Task.objects.get(id=int(task_id), assigned_to=user)
    except (Task.DoesNotExist, ValueError, TypeError):
        try:
            task = Task.objects.get(task_id=task_id, assigned_to=user)
        except Task.DoesNotExist:
            return Response({'error': 'Task not found or not assigned to you'}, status=404)

    # ✅ Fetch site latitude/longitude from SiteData
    site_lat, site_lon = None, None
    if hasattr(task, 'site') and task.site:   # If Task has FK to SiteData
        site_lat, site_lon = task.site.latitude, task.site.longitude
    elif hasattr(task, 'global_id'):          # Or match by global_id
        site = SiteData.objects.filter(global_id=task.global_id).first()
        if site:
            site_lat, site_lon = site.latitude, site.longitude

    # ✅ Geofencing check
    if user_lat and user_lon and site_lat and site_lon:
        try:
            user_lat = float(user_lat)
            user_lon = float(user_lon)
            site_lat = float(site_lat)
            site_lon = float(site_lon)

            distance = haversine(user_lat, user_lon, site_lat, site_lon)
            if distance > 100:  # Outside 100m
                return Response({
                    'error': 'You are outside the allowed 100m geofence',
                    'distance_m': round(distance, 2)
                }, status=403)

        except Exception:
            return Response({'error': 'Invalid latitude/longitude format'}, status=400)

    # Update task status
    if task.status != 'in_progress':
        task.status = 'in_progress'
        task.save()

    # Remove rejected reports
    Report.objects.filter(task=task, submitted_by=user, status='rejected').delete()

    # Create report
    report = Report.objects.create(
        task=task,
        submitted_by=user,
        data=form_data,
        status='in_progress'
    )

    # Handle file uploads
    for file_key, file in request.FILES.items():
        if file_key.startswith('file_'):
            label_key = 'file_label_' + file_key[5:]
            field_label = request.POST.get(label_key, '') or data.get(label_key, '')
            ReportFileUpload.objects.create(
                report=report,
                field_label=field_label,
                file=file,
                uploaded_by=user
            )

    return Response({'message': 'Report submitted', 'report_id': report.id})



@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_my_tasks(request):
    user = request.user
    tasks = Task.objects.filter(assigned_to=user).order_by('-assigned_date')

    task_list = []
    for task in tasks:
        report = task.reports.filter(submitted_by=user).order_by('-submitted_at').first()
        status = report.status if report else 'pending'

        task_list.append({
            'task_id': task.task_id,
            'task_type': task.type.name if task.type else "",
            'global_id': task.global_id,
            'site_name': task.site_name if hasattr(task, 'site_name') else "",
            'cluster_name': task.cluster.name if task.cluster else "",
            'assigned_date': task.assigned_date,
            'planned_date': task.planned_date,       # 🔹 added
            'deadline': task.deadline,               # 🔹 added
            'status': status,
            'employee_name': user.first_name,
            'employee_email': user.email,
            'assigned_by': task.assigned_by.first_name if task.assigned_by else '',
            'assigned_by_email': task.assigned_by.email if task.assigned_by else '',
        })
    return Response(task_list)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser])
def upload_report_file(request):
    user = request.user
    report_id = request.data.get('report_id')
    field_label = request.data.get('field_label')
    file = request.FILES.get('file')

    if not all([report_id, field_label, file]):
        return Response({'error': 'Missing report_id, field_label, or file'}, status=400)

    try:
        report = Report.objects.get(id=report_id, submitted_by=user)
    except Report.DoesNotExist:
        return Response({'error': 'Report not found or not yours'}, status=404)

    ReportFileUpload.objects.create(
        report=report,
        field_label=field_label,
        file=file
    )

    return Response({'message': 'File uploaded successfully'})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_reports(request):
    user = request.user
    reports = Report.objects.filter(submitted_by=user).select_related('task').order_by('-submitted_at')

    data = []
    for report in reports:
        task = report.task
        data.append({
            'report_id': report.id,
            'task_id': task.task_id,
            'task_type': task.type.name if task.type else "",
            'global_id': task.global_id,
            'site_name': task.site_name if hasattr(task, 'site_name') else "",
            'cluster_name': task.cluster.name if task.cluster else "",
            'planned_date': task.planned_date,       # 🔹 added
            'deadline': task.deadline,               # 🔹 added
            'status': report.status,
            'submitted_at': report.submitted_at,
            'approved_at': report.approved_at,
            'rejection_reason': report.rejection_reason if report.status == 'rejected' else None,
        })

    return Response(data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def view_my_report(request, report_id):
    user = request.user

    try:
        report = Report.objects.select_related('task').prefetch_related('files').get(id=report_id, submitted_by=user)
    except Report.DoesNotExist:
        return Response({'error': 'Report not found'}, status=404)

    task = report.task
    return Response({
        'report_id': report.id,
        'task_id': task.task_id,
        'task_type': task.type.name if task.type else "",
        'global_id': task.global_id,
        'site_name': task.site_name if hasattr(task, 'site_name') else "",
        'cluster_name': task.cluster.name if task.cluster else "",
        'planned_date': task.planned_date,         # 🔹 added
        'deadline': task.deadline,                 # 🔹 added
        'status': report.status,
        'submitted_at': report.submitted_at,
        'approved_at': report.approved_at,
        'rejection_reason': report.rejection_reason if report.status == 'rejected' else None,
        'form_data': report.data,
        'files': [
            {
                'label': f.field_label,
                'url': request.build_absolute_uri(f.file.url)
            }
            for f in report.files.all()
        ]
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_profile(request):
    user = request.user
    employee = getattr(user, 'employee_profile', None)

    return Response({
        'name': user.first_name,
        'email': user.email,
        'company_name': getattr(employee, 'company_name', None),
        'employee_id': getattr(employee, 'employee_id', None),
        'mobile_number': getattr(employee, 'mobile_number', None),
        'passport_photo': request.build_absolute_uri(employee.passport_photo.url)
            if employee and employee.passport_photo else None,
        'signature_photo': request.build_absolute_uri(employee.signature_photo.url)
            if employee and employee.signature_photo else None,
    })




@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def update_profile(request):
    user = request.user
    new_name = request.data.get('name')

    if not new_name:
        return Response({'error': 'Name is required'}, status=400)

    user.first_name = new_name
    user.save()
    return Response({'message': 'Name updated successfully'})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def change_password(request):
    user = request.user
    old_password = request.data.get('old_password')
    new_password = request.data.get('new_password')

    if not all([old_password, new_password]):
        return Response({'error': 'Old and new passwords are required'}, status=400)

    if not user.check_password(old_password):
        return Response({'error': 'Old password is incorrect'}, status=403)

    user.set_password(new_password)
    user.save()
    return Response({'message': 'Password changed successfully'})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dashboard_stats(request):
    total = Task.objects.count()
    completed = Task.objects.filter(status='completed').count()
    pending = Task.objects.filter(status='pending').count()
    in_progress = Task.objects.filter(status='in_progress').count()

    data = {
        'total_tasks': total,
        'completed_tasks': completed,
        'pending_tasks': pending,
        'in_progress_tasks': in_progress,
    }
    return Response(data)
