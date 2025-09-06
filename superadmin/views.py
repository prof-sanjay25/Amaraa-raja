from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Count

from authentication.models import User
from admin_panel.models import Task
from django.http import JsonResponse
from reports.models import Report
from sync.models import SyncConflict
from tasks.serializers import TaskSerializer
from authentication.models import User

from .serializers import (
    AdminUserSerializer,
    EmployeeUserSerializer,
    ReportSerializer,
    ConflictSerializer,
    SuperAdminProfileSerializer
)

# ✅ DASHBOARD
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def superadmin_dashboard_api(request):
    if request.user.role != 'superadmin':
        return Response({'error': 'Unauthorized'}, status=403)

    data = {
        'admins_count': User.objects.filter(role='admin').count(),
        'employees_count': User.objects.filter(role='employee').count(),
        'tasks_count': Task.objects.count(),
        'reports_count': Report.objects.count()
    }
    return Response(data)


# ✅ ADMIN MANAGEMENT
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def manage_admins(request):
    if request.user.role != 'superadmin':
        return Response({'error': 'Unauthorized'}, status=403)

    if request.method == 'GET':
        admins = User.objects.filter(role='admin')
        serializer = AdminUserSerializer(admins, many=True)
        return Response(serializer.data)

    if request.method == 'POST':
        data = request.data.copy()
        data['role'] = 'admin'

        # Validate passwords
        if data.get("password") != data.get("confirm_password"):
            return Response({'error': 'Passwords do not match'}, status=400)

        # Generate username
        first = data.get('first_name', '').strip().lower()
        last = data.get('last_name', '').strip().lower()
        data['username'] = f"{first}.{last}"

        serializer = AdminUserSerializer(data=data)
        if serializer.is_valid():
            admin = User.objects.create_user(
                username=data['username'],
                email=data['email'],
                first_name=first,
                last_name=last,
                state=data['state'],
                role='admin',
                password=data['password']
            )
            return Response(AdminUserSerializer(admin).data, status=201)
        return Response(serializer.errors, status=400)


@api_view(['PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def update_delete_admin(request, admin_id):
    if request.user.role != 'superadmin':
        return Response({'error': 'Unauthorized'}, status=403)

    try:
        admin = User.objects.get(id=admin_id, role='admin')
    except User.DoesNotExist:
        return Response({'error': 'Admin not found'}, status=404)

    if request.method == 'PUT':
        serializer = AdminUserSerializer(admin, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=400)

    if request.method == 'DELETE':
        admin.is_active = False
        admin.save()
        return Response({'message': 'Admin deactivated'})


# ✅ EMPLOYEE MANAGEMENT
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def manage_employees(request):
    if request.user.role == 'superadmin':
        employees = User.objects.filter(role='employee')
    elif request.user.role == 'admin':
        employees = User.objects.filter(role='employee', state=request.user.state)
    else:
        return Response({'error': 'Unauthorized'}, status=403)

    if request.method == 'GET':
        serializer = EmployeeUserSerializer(employees, many=True)
        return Response(serializer.data)

    if request.method == 'POST':
        data = request.data.copy()
        data['role'] = 'employee'
        if request.user.role == 'admin':
            data['state'] = request.user.state

        # Validate passwords
        if data.get("password") != data.get("confirm_password"):
            return Response({'error': 'Passwords do not match'}, status=400)

        # Generate username
        first = data.get('first_name', '').strip().lower()
        last = data.get('last_name', '').strip().lower()
        data['username'] = f"{first}.{last}"

        serializer = EmployeeUserSerializer(data=data)
        if serializer.is_valid():
            employee = User.objects.create_user(
                username=data['username'],
                email=data['email'],
                first_name=first,
                last_name=last,
                state=data['state'],
                role='employee',
                password=data['password']
            )
            return Response(EmployeeUserSerializer(employee).data, status=201)
        return Response(serializer.errors, status=400)


@api_view(['PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def update_delete_employee(request, employee_id):
    if request.user.role != 'superadmin':
        return Response({'error': 'Unauthorized'}, status=403)

    try:
        employee = User.objects.get(id=employee_id, role='employee')
    except User.DoesNotExist:
        return Response({'error': 'Employee not found'}, status=404)

    if request.method == 'PUT':
        serializer = EmployeeUserSerializer(employee, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=400)

    if request.method == 'DELETE':
        employee.is_active = False
        employee.save()
        return Response({'message': 'Employee deactivated'})


# ✅ REPORT MANAGEMENT
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_reports(request):
    role = request.user.role
    if role == 'superadmin':
        reports = Report.objects.all().order_by('-submitted_at')
    elif role == 'admin':
        reports = Report.objects.filter(submitted_by__state=request.user.state)
    elif role == 'employee':
        reports = Report.objects.filter(submitted_by=request.user)
    else:
        return Response({'error': 'Unauthorized'}, status=403)

    serializer = ReportSerializer(reports, many=True)
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def approve_report(request, report_id):
    if request.user.role != 'superadmin':
        return Response({'error': 'Unauthorized'}, status=403)

    try:
        report = Report.objects.get(id=report_id)
    except Report.DoesNotExist:
        return Response({'error': 'Report not found'}, status=404)

    report.status = 'approved'
    report.rejection_reason = ''
    report.save()
    return Response({'message': 'Report approved'})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def reject_report(request, report_id):
    if request.user.role != 'superadmin':
        return Response({'error': 'Unauthorized'}, status=403)

    reason = request.data.get('reason', '')
    if not reason:
        return Response({'error': 'Rejection reason required'}, status=400)

    try:
        report = Report.objects.get(id=report_id)
    except Report.DoesNotExist:
        return Response({'error': 'Report not found'}, status=404)

    report.status = 'rejected'
    report.rejection_reason = reason
    report.save()
    return Response({'message': 'Report rejected'})


# ✅ CONFLICT RESOLUTION
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_conflicts(request):
    if request.user.role != 'superadmin':
        return Response({'error': 'Unauthorized'}, status=403)

    conflicts = SyncConflict.objects.filter(is_resolved=False).order_by('-timestamp')
    serializer = ConflictSerializer(conflicts, many=True)
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def resolve_conflict(request, conflict_id):
    if request.user.role != 'superadmin':
        return Response({'error': 'Unauthorized'}, status=403)

    try:
        conflict = SyncConflict.objects.get(id=conflict_id)
    except SyncConflict.DoesNotExist:
        return Response({'error': 'Conflict not found'}, status=404)

    resolved_data = request.data.get('resolved_data')
    if not resolved_data:
        return Response({'error': 'Resolved data is required'}, status=400)

    conflict.resolved_data = resolved_data
    conflict.is_resolved = True
    conflict.save()
    return Response({'message': 'Conflict resolved successfully'})


# ✅ PROFILE MANAGEMENT
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def view_profile(request):
    if request.user.role != 'superadmin':
        return Response({'error': 'Unauthorized'}, status=403)

    serializer = SuperAdminProfileSerializer(request.user)
    return Response(serializer.data)


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def update_profile(request):
    if request.user.role != 'superadmin':
        return Response({'error': 'Unauthorized'}, status=403)

    serializer = SuperAdminProfileSerializer(request.user, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=400)


# ✅ TASK LIST & STATEWISE SUMMARY
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_all_tasks(request):
    if request.user.role != 'superadmin':
        return Response({'error': 'Unauthorized'}, status=403)

    state = request.query_params.get('state')
    tasks = Task.objects.filter(state=state) if state else Task.objects.all()

    serializer = TaskSerializer(tasks, many=True)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def statewise_summary(request):
    if request.user.role != 'superadmin':
        return Response({'error': 'Unauthorized'}, status=403)

    def group_by_state(qs, label):
        return {entry.get('state') or entry.get('submitted_by__state'): entry['count'] for entry in qs}

    return Response({
        'admins_by_state': group_by_state(User.objects.filter(role='admin').values('state').annotate(count=Count('id')), 'state'),
        'employees_by_state': group_by_state(User.objects.filter(role='employee').values('state').annotate(count=Count('id')), 'state'),
        'tasks_by_state': group_by_state(Task.objects.values('state').annotate(count=Count('id')), 'state'),
        'reports_by_state': group_by_state(Report.objects.values('submitted_by__state').annotate(count=Count('id')), 'submitted_by__state'),
    })


def state_task_summary(request):
    states = Task.objects.values_list('state', flat=True).distinct()
    summary = []

    for state in states:
        summary.append({
            "state": state,
            "completed": Task.objects.filter(state=state, status='completed').count(),
            "pending": Task.objects.filter(state=state, status='pending').count(),
            "in_progress": Task.objects.filter(state=state, status='in_progress').count(),
        })

    return JsonResponse(summary, safe=False)


def state_dashboard_summary(request):
    states = Task.objects.values_list('state', flat=True).distinct()
    summary = []

    for state in states:
        summary.append({
            "state": state,
            "completed": Task.objects.filter(state=state, status='completed').count(),
            "pending": Task.objects.filter(state=state, status='pending').count(),
            "in_progress": Task.objects.filter(state=state, status='in_progress').count(),
            "admin_count": User.objects.filter(state=state, role='admin').count(),
            "employee_count": User.objects.filter(state=state, role='employee').count()
        })

    return JsonResponse(summary, safe=False)