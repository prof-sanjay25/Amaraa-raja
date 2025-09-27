from __future__ import annotations
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from django.utils import timezone
from django.http import HttpResponse
from django.core.files.storage import default_storage
from django.contrib.auth import get_user_model
from .permissions import IsAdminOrSuperAdmin

from .models import Task, TaskType, Cluster
from superadmin.models import SiteData
from reports.models import Report
from .serializers import DashboardStatsSerializer

from django.template.loader import render_to_string
from weasyprint import HTML
import tempfile
import csv
from .audit import log_action
from django.db.models import F, Q


User = get_user_model()

from rest_framework.permissions import BasePermission

class IsAdminOrSuperAdmin(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user 
            and request.user.is_authenticated 
            and getattr(request.user, "role", "") in ["admin", "superadmin"]
        )


# views.py

from django.db.models import Count
from django.db.models.functions import TruncDate, TruncMonth
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from authentication.models import User
from .models import Task, Cluster
from .permissions import IsAdminOrSuperAdmin
from .serializers import DashboardStatsSerializer


@api_view(['GET'])
@permission_classes([IsAdminOrSuperAdmin])
def dashboard_stats(request):
    """
    Dashboard stats with filters and trend data.
    Filters supported:
      - from_date (YYYY-MM-DD)
      - to_date   (YYYY-MM-DD)
      - user_id
      - circle
      - cluster_id
    """
    user = request.user

    employees = User.objects.filter(role="employee")
    tasks = Task.objects.all()
    clusters = Cluster.objects.all()

    # 🔹 Restrict Admins to their own state only
    if user.role == "admin":
        employees = employees.filter(circle=user.circle)
        tasks = tasks.filter(assigned_to__circle=user.circle)
        clusters = clusters.filter(tasks__assigned_to__circle=user.circle).distinct()


    # =========================
    # 🔹 Apply filters
    # =========================
    from_date = request.GET.get("from_date")
    to_date = request.GET.get("to_date")
    user_id = request.GET.get("user_id")
    circle = request.GET.get("circle")
    cluster_id = request.GET.get("cluster_id")

    if from_date and to_date:
        tasks = tasks.filter(created_at__date__range=[from_date, to_date])

    if user_id:
        tasks = tasks.filter(assigned_to__id=user_id)

    if circle:
        tasks = tasks.filter(assigned_to__circle=circle)

    if cluster_id:
        tasks = tasks.filter(cluster_id=cluster_id)

    # =========================
    # 🔹 Task Types for Pie Chart
    # =========================
    TASK_TITLES = ["DG PM", "DG CM", "AC PM", "AC CM", "Site Visit"]

    task_type_stats = []
    for name in TASK_TITLES:
        task_qs = tasks.filter(title=name)
        task_type_stats.append({
            "task_name": name,
            "total": task_qs.count(),
            "completed": task_qs.filter(status="completed").count(),
            "pending": task_qs.filter(status="pending").count(),
            "wait_for_review": task_qs.filter(status="wait_for_review").count(),
            "color": "#1976D2",
        })

    # =========================
    # 🔹 Trend Data (Graph)
    # =========================
    # Group by day
    daily_trends = (
        tasks.annotate(day=TruncDate("created_at"))
        .values("day", "title", "status")
        .annotate(total=Count("id"))
        .order_by("day")
    )

    monthly_trends = (
        tasks.annotate(month=TruncMonth("created_at"))
        .values("month", "title", "status")
        .annotate(total=Count("id"))
        .order_by("month")
    )
    # =========================
    # 🔹 Clusters
    # =========================
    
    cluster_stats = list(
        tasks.values(
            "cluster__id",
            "cluster__name"
        )
        .annotate(
            total=Count("id"),
            completed=Count("id", filter=Q(status="completed")),
            pending=Count("id", filter=Q(status="pending")),
            wait_for_review=Count("id", filter=Q(status="wait_for_review")),
        )
    )
        # =========================
    # 🔹 Final Response
    # =========================
    stats = {
        "total_employees": employees.count(),
        "total_tasks": tasks.count(),
        "completed_tasks": tasks.filter(status="completed").count(),
        "pending_tasks": tasks.filter(status="pending").count(),
        "wait_for_review_tasks": tasks.filter(status="wait_for_review").count(),


        "task_type_stats": task_type_stats,
        "clusters": cluster_stats,

        "recent_assigned_tasks": [
            {
                "employee_id": t.assigned_to.id if t.assigned_to else None,
                "employee_name": t.assigned_to.first_name if t.assigned_to else "",
                "task_id": t.task_id,
                "task_type": t.type.name if t.type else "",
                "global_id": t.global_id,
            }
            for t in tasks.select_related("assigned_to", "type").order_by("-created_at")[:5]
        ],
        "recent_employees": [
            {
                "id": e.id,
                "name": e.first_name,
                "email": e.email,
                "designation": getattr(e, "designation", ""),
                "global_id": getattr(e, "global_id", ""),
                "state_user_id": getattr(e, "state_user_id", ""),
                "circle": getattr(e, "circle", ""),
                "active": e.is_active,
                "date_joined": e.date_joined,
            }
            for e in employees.order_by("-date_joined")[:5]
        ],
    }

    serializer = DashboardStatsSerializer(stats)
    return Response(serializer.data)



# admin_panel/views.py

from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from .permissions import IsAdminOrSuperAdmin
from superadmin.models import SiteData

@api_view(['GET'])
@permission_classes([IsAdminOrSuperAdmin])
def suggest_global_ids(request):
    """
    Return list of Global IDs for site selection.
    Admins → only their own circle
    Superadmins → all
    """
    user = request.user

    sites = SiteData.objects.all()
    if user.role == "admin":
        sites = sites.filter(circle__iexact=user.circle)


    data = [
        {
            "global_id": site.global_id,
            "site_name": site.site_name,
            "cluster_name": site.cluster_name,
            "circle": site.circle  # ✅
        }
        for site in sites.order_by("global_id")
    ]

    return Response(data)



# views.py

import csv
import io
import datetime as dt
from dataclasses import dataclass
from typing import Dict, Any, Optional, Tuple

from django.db import transaction
from django.core.exceptions import ValidationError
from django.http import HttpRequest

from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework import status

from .permissions import IsAdminOrSuperAdmin
from .audit import log_action

from admin_panel.models import Task, TaskType, Cluster
from superadmin.models import SiteData
from authentication.models import User

# ======================
# Config / Constants
# ======================

DATE_FORMATS = (
    "%Y-%m-%d",  # 2025-09-25
    "%d-%m-%Y",  # 25-09-2025
    "%d/%m/%Y",  # 25/09/2025
    "%d-%m-%y",  # 25-09-25
    "%d/%m/%y",  # 25/09/25
)

MAX_CSV_BYTES = 10 * 1024 * 1024  # 10 MB

CSV_HEADER_MAP = {
    "employee_email": "employee_email",
    "employee": "employee_email",
    "email": "employee_email",

    "task_name": "task_name",
    "title": "task_name",
    "name": "task_name",

    "task_type": "task_type",

    "global_id": "global_id",
    "gid": "global_id",

    "planned_date": "planned_date",
    "plan_date": "planned_date",
    "planned": "planned_date",

    "deadline": "deadline",
    "due_date": "deadline",

    "description": "description",
    "desc": "description",
}

REQUIRED_HEADERS = {"employee_email", "task_name", "task_type", "global_id", "planned_date"}


# ======================
# Utilities
# ======================

def _parse_date(value: str | None) -> Optional[dt.date]:
    if not value:
        return None
    val = str(value).strip()
    for fmt in DATE_FORMATS:
        try:
            return dt.datetime.strptime(val, fmt).date()
        except ValueError:
            continue
    raise ValidationError(f"Invalid date '{value}'. Allowed formats: {', '.join(DATE_FORMATS)}")


def _detect_delimiter(sample: str) -> str:
    if "\t" in sample and "," not in sample:
        return "\t"
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=[",", "\t", ";", "|"])
        return dialect.delimiter
    except Exception:
        return ","


def _normalize_headers(headers: list[str]) -> list[str]:
    norm = []
    for h in headers:
        if not h:
            continue
        key = h.strip().lower()
        norm.append(CSV_HEADER_MAP.get(key, key))
    return norm


def _user_scope_check(request_user: User, site: SiteData) -> Optional[str]:
    if getattr(request_user, "role", None) == "admin":
        if getattr(request_user, "circle", None) != getattr(site, "circle", None):
            return f"You cannot assign tasks outside your circle ({request_user.circle})"
    return None


def _find_duplicate_task(global_id: str, employee: User, title: str, planned_date: Optional[dt.date]) -> Optional[Task]:
    filters = {"global_id": global_id, "assigned_to": employee, "title": title}
    if planned_date is not None:
        filters["planned_date"] = planned_date
    else:
        filters["planned_date__isnull"] = True
    return Task.objects.filter(**filters).first()


@dataclass
class AssignInput:
    request_user: User
    global_id: str
    employee_email: str
    task_name: str
    task_type_name: str
    planned_date: Optional[dt.date] = None
    deadline: Optional[dt.date] = None
    description: str = ""
    update_if_exists: bool = False


def _task_to_payload(t: Task) -> Dict[str, Any]:
    return {
        "task_id": t.task_id,
        "employee_email": getattr(t.assigned_to, "email", ""),
        "title": t.title,
        "status": t.status,
        "type": t.type.name if t.type_id else None,
        "cluster_name": t.cluster_name,
        "site_name": t.site_name,
        "global_id": t.global_id,
        "circle": t.site.circle if t.site else None,
        "planned_date": t.planned_date.isoformat() if t.planned_date else None,
        "deadline": t.deadline.isoformat() if getattr(t, "deadline", None) else None,
        "description": t.description or "",
    }


# ======================
# Core helper
# ======================

def assign_task_core(data: AssignInput) -> Tuple[bool, Dict[str, Any], Optional[Task]]:
    try:
        site = SiteData.objects.get(global_id=data.global_id)
    except SiteData.DoesNotExist:
        return False, {"error": "Invalid Global ID"}, None

    scope_err = _user_scope_check(data.request_user, site)
    if scope_err:
        return False, {"error": scope_err}, None

    try:
        employee = User.objects.get(email=data.employee_email, role="employee")
    except User.DoesNotExist:
        return False, {"error": "Invalid employee_email"}, None

    task_type, _ = TaskType.objects.get_or_create(name=data.task_type_name, defaults={"color_code": "#888888"})
    cluster, _ = Cluster.objects.get_or_create(name=site.cluster_name)

    existing = _find_duplicate_task(data.global_id, employee, data.task_name, data.planned_date)

    try:
        with transaction.atomic():
            if existing:
                if data.update_if_exists:
                    existing.type = task_type
                    existing.cluster = cluster
                    existing.site = site
                    existing.site_name = site.site_name
                    existing.cluster_name = site.cluster_name
                    if data.description:
                        existing.description = data.description
                    if data.deadline is not None:
                        existing.deadline = data.deadline
                    existing.save()

                    log_action(
                        user=data.request_user,
                        action="ASSIGN_TASK_UPDATE",
                        target_type="Task",
                        target_id=existing.task_id,
                        details={
                            "reason": "duplicate_update",
                            "employee_email": employee.email,
                            "task_name": existing.title,
                            "planned_date": existing.planned_date.isoformat() if existing.planned_date else None,
                            "circle": site.circle,
                        },
                    )
                    return True, {"message": "Task updated (duplicate)", **_task_to_payload(existing)}, existing
                else:
                    log_action(
                        user=data.request_user,
                        action="ASSIGN_TASK_DUPLICATE_SKIPPED",
                        target_type="Task",
                        target_id=existing.task_id,
                        details={
                            "employee_email": employee.email,
                            "task_name": existing.title,
                            "planned_date": existing.planned_date.isoformat() if existing.planned_date else None,
                            "circle": site.circle,
                        },
                    )
                    return False, {"error": "Duplicate task (skipped)", **_task_to_payload(existing)}, existing

            task = Task.objects.create(
                global_id=data.global_id,
                title=data.task_name,
                description=data.description or "",
                status="pending",
                type=task_type,
                cluster=cluster,
                assigned_to=employee,
                deadline=data.deadline,
                planned_date=data.planned_date,
                site=site,
                site_name=site.site_name,
                cluster_name=site.cluster_name,
                assigned_by=data.request_user,
            )

            log_action(
                user=data.request_user,
                action="ASSIGN_TASK",
                target_type="Task",
                target_id=task.task_id,
                details={
                    "employee_email": employee.email,
                    "task_name": task.title,
                    "planned_date": task.planned_date.isoformat() if task.planned_date else None,
                    "circle": site.circle,
                },
            )
            return True, {"message": "Task assigned", **_task_to_payload(task)}, task

    except Exception as ex:
        log_action(
            user=data.request_user,
            action="ASSIGN_TASK_ERROR",
            target_type="Task",
            target_id=None,
            details={"error": str(ex), "employee_email": data.employee_email, "task_name": data.task_name,
                     "global_id": data.global_id},
        )
        return False, {"error": "Internal error while assigning task"}, None


# ======================
# API: Single assignment
# ======================

@api_view(["POST"])
@permission_classes([IsAdminOrSuperAdmin])
def assign_task(request: HttpRequest):
    payload = request.data or {}
    required = ("global_id", "employee_email", "task_name", "task_type")
    missing = [k for k in required if not payload.get(k)]
    if missing:
        return Response({"error": f"Missing fields: {', '.join(missing)}"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        planned_date = _parse_date(payload.get("planned_date"))
        deadline = _parse_date(payload.get("deadline"))
    except ValidationError as ve:
        return Response({"error": str(ve)}, status=status.HTTP_400_BAD_REQUEST)

    assign_input = AssignInput(
        request_user=request.user,
        global_id=str(payload["global_id"]).strip(),
        employee_email=str(payload["employee_email"]).strip(),
        task_name=str(payload["task_name"]).strip(),
        task_type_name=str(payload["task_type"]).strip(),
        planned_date=planned_date,
        deadline=deadline,
        description=str(payload.get("description", "")).strip(),
        update_if_exists=bool(payload.get("update_if_exists", False)),
    )

    ok, result, _ = assign_task_core(assign_input)
    return Response(result, status=status.HTTP_200_OK if ok else status.HTTP_400_BAD_REQUEST)


# ======================
# API: Bulk CSV assignment
# ======================

@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser])
@permission_classes([IsAdminOrSuperAdmin])
def bulk_assign_task_csv(request: HttpRequest):
    """
    Multipart form-data:
      - file: CSV file
      - update_if_exists: "true"|"false" (optional, default false)
      - atomic: "true"|"false" (optional, default false)

    Required headers:
      employee_email, task_name, task_type, global_id, planned_date
    """

    # 1) Ensure file exists
    if "file" not in request.FILES:
        return Response({"error": "CSV file is required"}, status=400)

    file = request.FILES["file"]
    decoded_file = file.read().decode("utf-8-sig")

    # 2) Detect delimiter (tab or comma)
    delimiter = "\t" if "\t" in decoded_file and "," not in decoded_file else ","

    reader = csv.DictReader(io.StringIO(decoded_file), delimiter=delimiter)
    if not reader.fieldnames:
        return Response({"error": "CSV file has no headers"}, status=400)

    # Normalize headers
    reader.fieldnames = [h.strip().lower() for h in reader.fieldnames if h]
    missing = REQUIRED_HEADERS - set(reader.fieldnames)
    if missing:
        return Response({"error": f"Missing required headers: {', '.join(sorted(missing))}"}, status=400)

    update_if_exists = str(request.data.get("update_if_exists", "false")).lower() == "true"
    atomic_all = str(request.data.get("atomic", "false")).lower() == "true"

    results: list[Dict[str, Any]] = []
    errors_count = 0

    def _process_row(idx: int, row: Dict[str, str]) -> Dict[str, Any]:
        # Normalize row (keys and values)
        row = {k.strip().lower(): (v.strip() if v else "") for k, v in row.items()}

        # Required fields check
        for key in REQUIRED_HEADERS:
            if not row.get(key):
                return {"row": idx, "error": f"Missing required field '{key}'", "data": row}

        # Parse dates
        try:
            planned_date = _parse_date(row.get("planned_date"))
            deadline = _parse_date(row.get("deadline"))
        except ValidationError as ve:
            return {"row": idx, "error": str(ve), "data": row}

        # Build input for core assign function
        assign_input = AssignInput(
            request_user=request.user,
            global_id=row["global_id"],
            employee_email=row["employee_email"],
            task_name=row["task_name"],
            task_type_name=row["task_type"],
            planned_date=planned_date,
            deadline=deadline,
            description=row.get("description", "") or "",
            update_if_exists=update_if_exists,
        )

        ok, payload, _ = assign_task_core(assign_input)
        if ok:
            return {"row": idx, **payload}
        else:
            return {"row": idx, **payload, "data": row}

    # 3) Run rows
    if atomic_all:
        try:
            with transaction.atomic():
                for idx, row in enumerate(reader, start=2):
                    res = _process_row(idx, row)
                    if "error" in res:
                        raise ValidationError(f"Row {idx}: {res.get('error')}")
                    results.append(res)
        except ValidationError as ve:
            return Response(
                {"results": results, "error": f"Atomic bulk failed: {str(ve)}"},
                status=400,
            )
    else:
        for idx, row in enumerate(reader, start=2):
            res = _process_row(idx, row)
            if "error" in res:
                errors_count += 1
            results.append(res)

        if not results or len(results) == errors_count:
            return Response({"results": results, "message": "No tasks created"}, status=400)

    return Response(
        {
            "results": results,
            "delimiter_used": delimiter,
            "updated_on_duplicate": update_if_exists,
            "mode": "atomic" if atomic_all else "partial",
        },
        status=200,
    )



# ======================
# API: Bulk CSV Template
# ======================

@api_view(["GET"])
@permission_classes([IsAdminOrSuperAdmin])
def bulk_assign_csv_template(request: HttpRequest):
    """
    Return a reference CSV template for bulk task assignment.
    Only required headers are included.
    """

    headers = [
        "employee_email",  # required
        "task_name",       # required
        "task_type",       # required
        "global_id",       # required
        "planned_date",    # required
    ]

    sample_rows = [
        [
            "john.doe@company.com",
            "DG PM",
            "Full Services",
            "453337",
            "2025-09-26",
        ],
        [
            "jane.smith@company.com",
            "AC CM",
            "TOH",
            "453338",
            "2025-09-27",
        ],
    ]

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    writer.writerows(sample_rows)

    response = HttpResponse(output.getvalue(), content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="bulk_tasks_template.csv"'
    return response




from rest_framework.decorators import api_view, permission_classes
from .permissions import IsAdminOrSuperAdmin

from rest_framework.response import Response
from .models import Task
from .pagination import StandardResultsSetPagination

@api_view(['GET'])
@permission_classes([IsAdminOrSuperAdmin])
def list_tasks(request):
    user = request.user
    status = request.GET.get('status')

    queryset = Task.objects.select_related(
        'assigned_to',
        'assigned_to__employee_profile',
        'type',
        'cluster',
        'assigned_by',
        'site'
    ).order_by('-created_at')

    # 🔹 Restrict Admins
    if user.role == "admin":
        queryset = queryset.filter(
            assigned_to__circle=user.circle,
            assigned_to__employee_profile__manager=user
        )

    if status:
        queryset = queryset.filter(status=status)

    paginator = StandardResultsSetPagination()
    page = paginator.paginate_queryset(queryset, request)

    data = []
    for t in page:
        # Resolve site name
        if getattr(t, 'site_name', None):
            resolved_site_name = t.site_name
        elif getattr(t, 'site', None):
            resolved_site_name = t.site.site_name
        else:
            resolved_site_name = ''

        # Fetch lat/lon from SiteData relation
        site_lat = t.site.latitude if t.site and t.site.latitude else None
        site_lon = t.site.longitude if t.site and t.site.longitude else None

        data.append({
            'task_id': t.task_id,
            'global_id': t.global_id,
            'task_name': t.title,
            'task_type': t.type.name if t.type else '',
            'status': t.status,
            'assigned_date': t.created_at,
            'deadline': t.deadline,
            'planned_date': t.planned_date,
            'cluster_name': t.cluster.name if t.cluster else '',
            'site_name': resolved_site_name,
            'site_lat': float(site_lat) if site_lat else None,
            'site_lon': float(site_lon) if site_lon else None,
            'employee_id': t.assigned_to.id if t.assigned_to else None,
            'employee_name': t.assigned_to.first_name if t.assigned_to else '',
            'employee_email': t.assigned_to.email if t.assigned_to else '',
            'employee_global_id': getattr(t.assigned_to, 'global_id', '') if t.assigned_to else '',
            'employee_state_user_id': getattr(t.assigned_to, 'state_user_id', '') if t.assigned_to else '',
            'employee_circle': getattr(t.assigned_to, 'circle', '') if t.assigned_to else '',
            'assigned_by_id': t.assigned_by.id if t.assigned_by else None,
            'assigned_by_name': t.assigned_by.first_name if t.assigned_by else '',
            'assigned_by_email': t.assigned_by.email if t.assigned_by else '',
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

    return paginator.get_paginated_response(data)



# Task type to form group and full title mapping
TASK_TYPE_MAPPING = {
    # DG – Preventive
    'FULL SERVICES': ('dg_pm_cm', 'DG Preventive Maintenance Field Service Report'),
    'TOP-UP':        ('dg_pm_cm', 'DG Preventive Maintenance Field Service Report'),
    'DG PM':         ('dg_pm_cm', 'DG Preventive Maintenance Field Service Report'),

    # DG – Corrective
    'DG CM': ('dg_pm_cm', 'DG Corrective Maintenance Field Service Report'),
    'CM':    ('dg_pm_cm', 'DG Corrective Maintenance Field Service Report'),
    'TOH':   ('dg_pm_cm', 'DG Corrective Maintenance Field Service Report'),
    'MOH':   ('dg_pm_cm', 'DG Corrective Maintenance Field Service Report'),

    # AC
    'AC PM': ('ac_pm_cm', 'AC Preventive Maintenance Field Service Report'),
    'AC CM': ('ac_pm_cm', 'AC Corrective Maintenance Field Service Report'),

    # Site Visit
    'SITE VISIT': ('site_visit', 'Site Visit Field Service Report'),
}

def get_form_group_and_title(task_type: str):
    if not task_type:
        return 'dg_pm_cm', 'DG Preventive Maintenance Field Service Report'

    t = task_type.strip().upper()

    # 1) Exact map first
    if t in TASK_TYPE_MAPPING:
        return TASK_TYPE_MAPPING[t]

    # 2) DG Corrective vs Preventive
    if 'DG' in t or 'GENERATOR' in t:
        if any(k in t for k in [' CM', 'CM ', 'CM', 'TOH', 'MOH', 'CORRECTIVE']):
            return 'dg_pm_cm', 'DG Corrective Maintenance Field Service Report'
        if any(k in t for k in [' PM', 'PM ', 'PM', 'PREVENTIVE', 'FULL', 'TOP']):
            return 'dg_pm_cm', 'DG Preventive Maintenance Field Service Report'

    # 3) AC
    if 'AC' in t or 'AIR CONDITION' in t:
        if any(k in t for k in [' CM', 'CM ', 'CM', 'CORRECTIVE']):
            return 'ac_pm_cm', 'AC Corrective Maintenance Field Service Report'
        return 'ac_pm_cm', 'AC Preventive Maintenance Field Service Report'

    # 4) Site visit
    if any(k in t for k in ['SITE', 'VISIT', 'INSPECTION']):
        return 'site_visit', 'Site Visit Field Service Report'

    # Default
    return 'dg_pm_cm', 'DG Preventive Maintenance Field Service Report'


def get_form_group_and_title(task_type: str):
    if not task_type:
        return 'dg_pm_cm', 'DG Preventive Maintenance Field Service Report'

    t = task_type.strip().upper()

    # 1) Exact map first
    if t in TASK_TYPE_MAPPING:
        return TASK_TYPE_MAPPING[t]

    # 2) DG Corrective vs Preventive
    if 'DG' in t or 'GENERATOR' in t:
        if any(k in t for k in [' CM', 'CM ', 'CM', 'TOH', 'MOH', 'CORRECTIVE']):
            return 'dg_pm_cm', 'DG Corrective Maintenance Field Service Report'
        if any(k in t for k in [' PM', 'PM ', 'PM', 'PREVENTIVE', 'FULL', 'TOP']):
            return 'dg_pm_cm', 'DG Preventive Maintenance Field Service Report'

    # 3) AC
    if 'AC' in t or 'AIR CONDITION' in t:
        if any(k in t for k in [' CM', 'CM ', 'CM', 'CORRECTIVE']):
            return 'ac_pm_cm', 'AC Corrective Maintenance Field Service Report'
        return 'ac_pm_cm', 'AC Preventive Maintenance Field Service Report'

    # 4) Site visit
    if any(k in t for k in ['SITE', 'VISIT', 'INSPECTION']):
        return 'site_visit', 'Site Visit Field Service Report'

    # Default
    return 'dg_pm_cm', 'DG Preventive Maintenance Field Service Report'




@api_view(['DELETE'])
@permission_classes([IsAdminOrSuperAdmin])
def delete_task(request, task_id):
    try:
        task = Task.objects.get(task_id=task_id)
    except Task.DoesNotExist:
        return Response({'error': 'Task not found'}, status=404)

    log_action(
        user=request.user,
        action="DELETE_TASK",
        target_type="Task",
        target_id=task.task_id,
        details={"task_name": task.title}
    )
    task.delete()
    return Response({'message': 'Task deleted'})





@api_view(['GET'])
@permission_classes([IsAdminOrSuperAdmin])
def list_reports(request):
    user = request.user

    reports = Report.objects.select_related(
        'task',
        'submitted_by',
        'submitted_by__employee_profile',
        'task__cluster',
        'task__assigned_by'
    ).order_by('-submitted_at')

    # 🔹 Restrict admins
    if user.role == "admin":
        reports = reports.filter(
            submitted_by__circle=user.circle,
            submitted_by__employee_profile__manager=user
        )

    paginator = StandardResultsSetPagination()
    page = paginator.paginate_queryset(reports, request)

    data = []
    for r in page:
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
            'employee_circle': getattr(r.submitted_by, 'circle', ''),
            'assigned_date': r.task.created_at,
            'submitted_date': r.submitted_at,
            'admin_name': r.task.assigned_by.first_name if r.task.assigned_by else '',
            'admin_email': r.task.assigned_by.email if r.task.assigned_by else '',
            'status': r.status,
        })

    return paginator.get_paginated_response(data)




from .audit import log_action  # import the helper we made

@api_view(['POST'])
@permission_classes([IsAdminOrSuperAdmin])
def review_report(request):
    report_id = request.data.get('report_id')
    action = request.data.get('action')
    reason = request.data.get('reason', '')

    try:
        report = Report.objects.select_related(
            'task',
            'submitted_by',
            'submitted_by__employee_profile'
        ).get(id=report_id)
    except Report.DoesNotExist:
        return Response({'error': 'Report not found'}, status=404)

    user = request.user

    # 🔹 Restrict Admins (Superadmins skip this)
    if user.role == "admin":
        employee = getattr(report.submitted_by, "employee_profile", None)

        # Must be linked to an employee
        if not employee:
            return Response({'error': 'Report is not linked to an employee'}, status=403)

        # Must be in the same state
        if report.submitted_by.circle != user.circle:
            return Response({'error': 'You cannot review reports outside your circle'}, status=403)


        # Must be the employee’s reporting manager
        if employee.manager_id != user.id:
            return Response({'error': 'You are not the reporting manager for this employee'}, status=403)

    # 🔹 Proceed with action
    if action == 'approve':
        report.status = 'approved'
        report.approved_at = timezone.now()
        report.task.status = 'completed'
        report.task.save()

        log_action(
            user=request.user,
            action="APPROVE_REPORT",
            target_type="Report",
            target_id=report.id,
            details={
                "task_id": report.task.task_id,
                "global_id": report.task.global_id,
                "site_name": report.task.site_name
            }
        )

    elif action == 'reject':
        report.status = 'rejected'
        report.rejection_reason = reason
        report.task.status = 'pending'
        report.task.save()

        log_action(
            user=request.user,
            action="REJECT_REPORT",
            target_type="Report",
            target_id=report.id,
            details={
                "reason": reason,
                "task_id": report.task.task_id,
                "global_id": report.task.global_id,
                "site_name": report.task.site_name
            }
        )
    else:
        return Response({'error': 'Invalid action'}, status=400)

    report.save()
    return Response({'message': f'Report {action}d'})





@api_view(['GET'])
@permission_classes([IsAdminOrSuperAdmin])
def list_admins(request):
    user = request.user

    # Include both admins and superadmins
    admins = User.objects.filter(role__in=['admin'])

    # Restrict regular admins to their own circle
    if user.role == "admin":
        admins = admins.filter(circle=user.circle)

    data = [{
        'id': admin.id,
        'name': admin.first_name,
        'email': admin.email,
        'role': admin.role,
        'circle': admin.circle,
    } for admin in admins]

    return Response(data)



# --- 5. Employee Management ---

from rest_framework.decorators import api_view, permission_classes
from .permissions import IsAdminOrSuperAdmin

from rest_framework.response import Response
from django.contrib.auth import get_user_model
from employees.models import Employee
from django.core.exceptions import ValidationError

User = get_user_model()

@api_view(['POST'])
@permission_classes([IsAdminOrSuperAdmin])
def create_employee(request):
    admin = request.user

    # Required fields
    name = request.data.get('name')
    email = request.data.get('email')
    password = request.data.get('password')
    confirm_password = request.data.get('confirm_password')
    user_type = request.data.get('user_type')
    user_role = request.data.get('user_role')
    company_name = request.data.get('company_name')
    employee_id = request.data.get('employee_id')
    mobile_number = request.data.get('mobile_number')
    manager_id = request.data.get('manager_id')

    passport_photo = request.FILES.get('passport_photo')
    signature_photo = request.FILES.get('signature_photo')

    # --- Validation: Required fields ---
    missing = []
    if not name: missing.append("name")
    if not email: missing.append("email")
    if not password: missing.append("password")
    if not confirm_password: missing.append("confirm_password")
    if not user_type: missing.append("user_type")
    if not user_role: missing.append("user_role")
    if not company_name: missing.append("company_name")
    if not employee_id: missing.append("employee_id")
    if not mobile_number: missing.append("mobile_number")
    if not passport_photo: missing.append("passport_photo")
    if not signature_photo: missing.append("signature_photo")
    if not manager_id: missing.append("manager_id")

    if missing:
        return Response({"error": f"Missing required fields: {', '.join(missing)}"}, status=400)

    # --- Validation: Password ---
    if password != confirm_password:
        return Response({'error': 'Passwords do not match'}, status=400)

    try:
        User.validate_password_strength(password)
    except ValidationError as e:
        return Response({'error': str(e)}, status=400)

    # --- Validation: Email ---
    if User.objects.filter(email=email).exists():
        return Response({'error': 'Email already exists'}, status=400)

    # --- Validation: Mobile Number ---
    if not mobile_number.isdigit() or len(mobile_number) != 10:
        return Response({'error': 'Mobile number must be exactly 10 digits'}, status=400)

    # --- Validate manager ---
    try:
        manager = User.objects.get(id=manager_id)
    except User.DoesNotExist:
        return Response({'error': 'Manager not found'}, status=404)

    if manager.role not in ['admin', 'superadmin']:
        return Response({'error': 'Manager must be an admin or superadmin'}, status=400)



    # --- Create User ---
    user = User.objects.create_user(
        username=name,
        email=email,
        password=password,
        first_name=name,
        circle=admin.circle,  # state inherited from admin
        role='employee',
        is_active=True
    )

    # --- Create Employee Profile ---
    employee = Employee.objects.create(
        user=user,
        company_name=company_name,
        employee_id=employee_id,
        mobile_number=mobile_number,
        passport_photo=passport_photo,
        signature_photo=signature_photo,
        user_type=user_type,
        user_role=user_role,
        manager=manager
    )

    return Response({
        'message': 'Employee created successfully',
        'user_id': user.id,
        'global_id': user.global_id,
        'state_user_id': user.state_user_id,
        'employee_id': employee.employee_id,
        'user_type': employee.user_type,
        'user_role': employee.user_role,
    }, status=201)



import zipfile, tempfile, os, csv
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.decorators import api_view, permission_classes, parser_classes
from .permissions import IsAdminOrSuperAdmin

from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from employees.models import Employee

User = get_user_model()


import zipfile, tempfile, os, csv, mimetypes
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from employees.models import Employee
from .permissions import IsAdminOrSuperAdmin

User = get_user_model()



def find_photo_anywhere(temp_dir, email, kind):
    """
    Search recursively for photo files by email and type (passport/signature).
    Works with .jpg/.jpeg/.png and case-insensitive.
    """
    base_name = f"{email.lower()}_{kind}"
    for root, dirs, files in os.walk(temp_dir):
        for f in files:
            name, ext = os.path.splitext(f.lower())
            # Strip duplicate .jpg.jpg
            if ext in [".jpg", ".jpeg", ".png"] or name.endswith((".jpg", ".jpeg", ".png")):
                clean_name = name
                for ext in [".jpg", ".jpeg", ".png"]:
                    clean_name = clean_name.replace(ext, "")
                if clean_name == base_name:
                    return os.path.join(root, f)


    return None


from PIL import Image
import io

def make_uploaded_file(path):
    if not path or not os.path.exists(path):
        return None

    with open(path, "rb") as f:
        data = f.read()
        if not data:
            return None

    try:
        img = Image.open(io.BytesIO(data))
        img.load()  # ✅ Actually load pixel data
        format_ext = img.format.lower()
    except Exception as e:
        print(f"⚠️ Invalid image file {path}: {e}")
        return None

    mime = f"image/{'jpeg' if format_ext == 'jpg' else format_ext}"

    return SimpleUploadedFile(
        name=os.path.basename(path),
        content=data,
        content_type=mime,
    )




@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser])
@permission_classes([IsAdminOrSuperAdmin])
def bulk_create_employees_zip(request):
    """
    Bulk create employees from a ZIP file containing employees.csv + photos/.
    CSV must include headers:
      name, email, password, confirm_password,
      company_name, employee_id, mobile_number,
      user_type, user_role, manager_email

    Photos must be named:
      <email>_passport(.jpg/.jpeg/.png)
      <email>_signature(.jpg/.jpeg/.png)
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
        for f in files:
            if f.lower() == "employees.csv":
                csv_path = os.path.join(root, f)
                break
        if csv_path:
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
            user_type = row.get('user_type')
            user_role = row.get('user_role')
            manager_email = row.get('manager_email')

            # --- Validation ---
            missing = []
            for field, label in [
                (name, "name"), (email, "email"),
                (password, "password"), (confirm_password, "confirm_password"),
                (company_name, "company_name"), (employee_id, "employee_id"),
                (mobile_number, "mobile_number"),
                (user_type, "user_type"), (user_role, "user_role"),
                (manager_email, "manager_email"),
            ]:
                if not field:
                    missing.append(label)
            if missing:
                results.append({'row': idx, 'error': f"Missing required fields: {', '.join(missing)}"})
                continue

            if password != confirm_password:
                results.append({'row': idx, 'error': 'Passwords do not match'})
                continue

            if User.objects.filter(email=email).exists():
                results.append({'row': idx, 'error': 'Email already exists'})
                continue

            if not mobile_number.isdigit() or len(mobile_number) != 10:
                results.append({'row': idx, 'error': 'Mobile number must be 10 digits'})
                continue

            try:
                User.validate_password_strength(password)
            except ValidationError as e:
                results.append({'row': idx, 'error': str(e)})
                continue

            # --- Validate manager by email ---
            try:
                manager = User.objects.get(email=manager_email)
            except User.DoesNotExist:
                results.append({'row': idx, 'error': f"Manager {manager_email} not found"})
                continue

            if manager.role not in ['admin', 'superadmin']:
                results.append({'row': idx, 'error': f"Manager {manager_email} is not allowed (must be admin/superadmin)"})
                continue

            # --- Create User ---
            user = User.objects.create_user(
                username=name,
                email=email,
                password=password,
                first_name=name,
                circle=admin.circle,
                role='employee',
                is_active=True
            )

            # --- Find & clean photos ---
            passport_file = make_uploaded_file(find_photo_anywhere(temp_dir, email, "passport"))
            signature_file = make_uploaded_file(find_photo_anywhere(temp_dir, email, "signature"))

            warnings = []
            if not passport_file:
                warnings.append("Passport photo missing or invalid")
            if not signature_file:
                warnings.append("Signature photo missing or invalid")

            # --- Create Employee profile ---
            employee = Employee.objects.create(
                user=user,
                company_name=company_name,
                employee_id=employee_id,
                mobile_number=mobile_number,
                passport_photo=passport_file,
                signature_photo=signature_file,
                user_type=user_type,
                user_role=user_role,
                manager=manager
            )
            print(f"Saving {email} → passport={bool(passport_file)} signature={bool(signature_file)}")


            results.append({
                'row': idx,
                'message': 'Employee created',
                'email': email,
                'user_id': user.id,
                'employee_id': employee.employee_id,
                'user_type': employee.user_type,
                'user_role': employee.user_role,
                'passport_photo_saved': bool(passport_file),
                'signature_photo_saved': bool(signature_file),
                'warnings': warnings,
            })

    return Response({'results': results})


import io, zipfile, csv
from django.http import HttpResponse
from rest_framework.decorators import api_view, permission_classes
from .permissions import IsAdminOrSuperAdmin


@api_view(['GET'])
@permission_classes([IsAdminOrSuperAdmin])
def bulk_employee_sample_zip(request):
    """
    Return a sample ZIP with employees.csv + photos/ folder.
    Now uses manager_email instead of manager_id.
    """
    buffer = io.BytesIO()

    with zipfile.ZipFile(buffer, "w") as zf:
        # --- employees.csv ---
        csv_buffer = io.StringIO()
        writer = csv.writer(csv_buffer)
        writer.writerow([
            "name", "email", "password", "confirm_password",
            "company_name", "employee_id", "mobile_number",
            "user_type", "user_role", "manager_email"
        ])
        writer.writerow([
            "John Doe", "john@example.com", "Pass@123", "Pass@123",
            "AREML Pvt Ltd", "EMP001", "9876543210",
            "AREML", "Technician", "admin@example.com"
        ])
        writer.writerow([
            "Jane Smith", "jane@example.com", "Pass@123", "Pass@123",
            "SWEAR Solutions", "EMP002", "9123456789",
            "SWEAR", "Supervisor", "admin@example.com"
        ])
        zf.writestr("employees.csv", csv_buffer.getvalue())

        # --- dummy photos/ ---
        zf.writestr("photos/john@example.com_passport.jpg", b"sample passport")
        zf.writestr("photos/john@example.com_signature.jpg", b"sample signature")
        zf.writestr("photos/jane@example.com_passport.jpg", b"sample passport")
        zf.writestr("photos/jane@example.com_signature.jpg", b"sample signature")

    buffer.seek(0)
    response = HttpResponse(buffer.getvalue(), content_type="application/zip")
    response['Content-Disposition'] = 'attachment; filename=employee_bulk_sample.zip'
    return response




# --- 5. Employee Management ---

from django.shortcuts import get_object_or_404

@api_view(['POST'])
@permission_classes([IsAdminOrSuperAdmin])
def toggle_employee_status(request, id):
    employee = get_object_or_404(User, id=id, role='employee')
    action = request.data.get('action')  # 'suspend' or 'activate'

    if action == 'suspend':
        employee.is_active = False
    elif action == 'activate':
        employee.is_active = True
    else:
        return Response({'status': 'error', 'message': 'Invalid action specified'}, status=400)
    

    log_action(
        user=request.user,
        action="TOGGLE_EMPLOYEE",
        target_type="Employee",
        target_id=employee.id,
        details={"new_status": employee.is_active}
    )

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
            'circle': employee.circle,
            'is_active': employee.is_active,
            'date_joined': employee.date_joined,
        }
    })


@api_view(['GET'])
@permission_classes([IsAdminOrSuperAdmin])
def list_employees(request):
    user = request.user

    employees = User.objects.filter(role='employee')

    # 🔹 Restrict Admins to their state only
    if user.role == "admin":
        employees = employees.filter(circle=user.circle)


    employees = employees.order_by('-date_joined')

    paginator = StandardResultsSetPagination()
    page = paginator.paginate_queryset(employees, request)

    data = []
    for e in page:
        profile = getattr(e, 'employee_profile', None)

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
            'circle': e.circle,
            'is_active': e.is_active,
            'date_joined': e.date_joined,
        })

    return paginator.get_paginated_response(data)




from django.shortcuts import get_object_or_404

@api_view(['GET'])
@permission_classes([IsAdminOrSuperAdmin])
def get_employee(request, id):
    user = request.user
    employee = get_object_or_404(User, id=id, role='employee')
    profile = getattr(employee, 'employee_profile', None)

    # 🔹 Restrict Admins to same state only
    if user.role == "admin" and employee.circle != user.circle:
        return Response({'error': 'You are not allowed to view this employee'}, status=403)


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
        'user_type': profile.user_type if profile else '',
        'user_role': profile.user_role if profile else '',
        'manager_id': profile.manager.id if profile and profile.manager else None,
        'passport_photo': build_url(profile.passport_photo) if profile else None,
        'signature_photo': build_url(profile.signature_photo) if profile else None,
        'global_id': employee.global_id,
        'state_user_id': employee.state_user_id,
        'circle': employee.circle,
        'is_active': employee.is_active,
        'date_joined': employee.date_joined,
    }
    return Response(data)





@api_view(['PUT'])
@permission_classes([IsAdminOrSuperAdmin])
def update_employee(request, id):
    employee = get_object_or_404(User, id=id, role='employee')
    profile, _ = Employee.objects.get_or_create(user=employee)

    # Update core user fields
    employee.first_name = request.data.get('name', employee.first_name)
    employee.email = request.data.get('email', employee.email)
    if 'is_active' in request.data:
        employee.is_active = request.data['is_active']
    if 'circle' in request.data:
        employee.circle = request.data['circle']
    employee.save()

    # Update employee profile fields
    profile.company_name = request.data.get('company_name', profile.company_name)
    profile.employee_id = request.data.get('employee_id', profile.employee_id)

    if 'mobile_number' in request.data:
        mobile_number = request.data['mobile_number']
        if not mobile_number.isdigit() or len(mobile_number) != 10:
            return Response({'error': 'Mobile number must be exactly 10 digits'}, status=400)
        profile.mobile_number = mobile_number

    if 'user_type' in request.data:
        profile.user_type = request.data['user_type']
    if 'user_role' in request.data:
        profile.user_role = request.data['user_role']

    if 'manager_id' in request.data:
        try:
            manager = User.objects.get(id=request.data['manager_id'])
            profile.manager = manager
        except User.DoesNotExist:
            return Response({'error': 'Manager not found'}, status=404)

    if 'passport_photo' in request.FILES:
        profile.passport_photo = request.FILES['passport_photo']
    if 'signature_photo' in request.FILES:
        profile.signature_photo = request.FILES['signature_photo']

    profile.save()

    return Response({'message': 'Employee updated successfully'})



@api_view(['DELETE'])
@permission_classes([IsAdminOrSuperAdmin])
def delete_employee(request, id):
    try:
        user = User.objects.get(id=id, role='employee')
        user.delete()
        return Response({'message': 'Employee deleted'})
    except User.DoesNotExist:
        return Response({'error': 'Employee not found'}, status=404)


import datetime

@api_view(['GET'])
@permission_classes([IsAdminOrSuperAdmin])
def export_employees_csv(request):
    user = request.user

    employees = User.objects.filter(role='employee')

    # 🔹 Restrict Admins to their state only
    if user.role == "admin":
        employees = employees.filter(circle=user.circle)


    # 🔹 Always generate unique filename with timestamp
    now = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"employee_details_{now}.csv"

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename={filename}'

    writer = csv.writer(response)

    writer.writerow([
        'Name', 'Email', 'Company Name', 'Employee ID',
        'Mobile Number', 'User Type', 'User Role',
        'Manager ID', 'circle', 'Is Active',
        'Date Joined', 'Passport Photo', 'Signature Photo',
    ])

    def build_url(file_field):
        if file_field and hasattr(file_field, 'url'):
            return request.build_absolute_uri(file_field.url)
        return ''

    for e in employees:
        profile = getattr(e, 'employee_profile', None)

        writer.writerow([
            e.first_name,
            e.email,
            profile.company_name if profile else '',
            profile.employee_id if profile else '',
            profile.mobile_number if profile else '',
            profile.user_type if profile else '',
            profile.user_role if profile else '',
            profile.manager.id if profile and profile.manager else '',
            e.circle,
            'Active' if e.is_active else 'Suspended',
            e.date_joined.strftime("%Y-%m-%d %H:%M:%S"),
            build_url(profile.passport_photo) if profile else '',
            build_url(profile.signature_photo) if profile else '',
        ])

    return response




from django.shortcuts import get_object_or_404
from .models import Admin  # your Admin model

@api_view(['GET', 'PUT'])
@permission_classes([IsAdminOrSuperAdmin])
def admin_profile(request):
    admin_user = request.user
    profile, _ = Admin.objects.get_or_create(user=admin_user)

    if request.method == 'GET':
        def build_url(file_field):
            if file_field and hasattr(file_field, 'url'):
                return request.build_absolute_uri(file_field.url)
            return None

        data = {
            'id': admin_user.id,
            'fullName': admin_user.first_name or admin_user.username,
            'email': admin_user.email,
            'role': admin_user.role,
            'global_id': admin_user.global_id,
            'state_user_id': admin_user.state_user_id,
            'circle': admin_user.circle,
            'is_active': admin_user.is_active,
            'date_joined': admin_user.date_joined,

            # 🔹 Extra profile fields
            'company_name': profile.company_name,
            'admin_id': profile.employee_id,
            'mobile_number': profile.mobile_number,
            'passport_photo': build_url(profile.passport_photo),
            'signature_photo': build_url(profile.signature_photo),
            'admin_type': profile.admin_type if hasattr(profile, 'admin_type') else None,
            'manager_id': profile.manager.id if profile.manager else None,
        }
        return Response(data)

    elif request.method == 'PUT':
        # Update base user
        name = request.data.get('fullName')
        if name:
            admin_user.first_name = name
        if 'circle' in request.data:
            admin_user.circle = request.data['circle']
        if 'is_active' in request.data:
            admin_user.is_active = request.data['is_active']
        admin_user.save()

        # Update profile
        profile.company_name = request.data.get('company_name', profile.company_name)
        profile.admin_id = request.data.get('admin_id', profile.admin_id)
        profile.mobile_number = request.data.get('mobile_number', profile.mobile_number)
        profile.admin_type = request.data.get('admin_type', getattr(profile, 'admin_type', None))

        if 'manager_id' in request.data:
            try:
                manager = User.objects.get(id=request.data['manager_id'], role='superadmin')
                profile.manager = manager
            except User.DoesNotExist:
                return Response({'error': 'Manager (Superadmin) not found'}, status=404)

        if 'passport_photo' in request.FILES:
            profile.passport_photo = request.FILES['passport_photo']
        if 'signature_photo' in request.FILES:
            profile.signature_photo = request.FILES['signature_photo']

        profile.save()

        return Response({'message': 'Profile updated successfully'})


# --- View Report ---
from django.utils.dateformat import format

@api_view(['GET'])
@permission_classes([IsAdminOrSuperAdmin])
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
@permission_classes([IsAdminOrSuperAdmin])
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







import io
import csv
import json
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils.timezone import localtime
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from weasyprint import HTML

from .permissions import IsAdminOrSuperAdmin
from reports.models import Report
from .models import AuditLog
from .pagination import StandardResultsSetPagination


from django.utils.dateparse import parse_datetime

def format_datetime(dt, default=""):
    if not dt:
        return default
    if isinstance(dt, str):
        # Try to parse ISO string
        parsed = parse_datetime(dt)
        if parsed:
            dt = parsed
        else:
            return dt  # fallback: return string directly
    try:
        return localtime(dt).strftime("%d-%m-%Y %H:%M")
    except Exception:
        return str(dt)

def safe_url(request, file_field):
    if file_field and hasattr(file_field, "url"):
        return request.build_absolute_uri(file_field.url)
    return None


# --- Export Report as CSV ---
@api_view(['GET'])
@permission_classes([IsAdminOrSuperAdmin])
def export_report_csv(request, report_id):
    try:
        report = Report.objects.select_related(
            'task', 'submitted_by', 'submitted_by__employee_profile'
        ).prefetch_related('files').get(id=report_id)
    except Report.DoesNotExist:
        return Response({'error': 'Report not found'}, status=404)

    user = request.user
    if user.role == "admin":
        if report.submitted_by.circle != user.circle:
            return Response({'error': 'You cannot export reports outside your circle'}, status=403)

        employee = getattr(report.submitted_by, "employee_profile", None)
        if not employee or employee.manager_id != user.id:
            return Response({'error': 'You are not the reporting manager for this employee'}, status=403)

    raw_data = report.data
    if isinstance(raw_data, str):
        try:
            raw_data = json.loads(raw_data)
        except Exception:
            raw_data = {}

    rows = []

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

    if hasattr(report, "files"):
        for f in report.files.all():
            rows.append({
                'section': 'Files',
                'label': f.field_label,
                'value': request.build_absolute_uri(f.file.url)
            })

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=['section', 'label', 'value'])
    writer.writeheader()
    for row in rows:
        writer.writerow(row)

    response = HttpResponse(buffer.getvalue(), content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename=report_{report.id}.csv'
    return response


from collections import OrderedDict
import csv, io, zipfile, json
from django.http import HttpResponse
from django.db.models import Q
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors

# --- Helpers ---
def flatten_report_data(data):
    """
    Recursively flatten report data into {label: value}.
    Preserves order as much as possible.
    """
    flat = OrderedDict()

    if isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, list):
                for item in v:
                    if isinstance(item, dict) and "label" in item:
                        flat[item["label"]] = item.get("value", "")
            elif isinstance(v, dict):
                flat.update(flatten_report_data(v))
            else:
                flat[k] = v
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and "label" in item:
                flat[item["label"]] = item.get("value", "")
            else:
                flat.update(flatten_report_data(item))
    return flat


# --- Bulk CSV Export ---
@api_view(['GET'])
@permission_classes([IsAdminOrSuperAdmin])
def export_tasks_csv(request):
    task_type = request.GET.get('task_type')

    queryset = Task.objects.prefetch_related('reports__files').all()
    if task_type:
        queryset = queryset.filter(title__icontains=task_type)

    groups = {
        "DG_PM_CM": queryset.filter(title__icontains="DG"),
        "AC_PM_CM": queryset.filter(title__icontains="AC"),
        "SITE_VISIT": queryset.filter(title__icontains="Site"),
    }

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as zipf:
        for group_name, tasks in groups.items():
            if not tasks.exists():
                continue

            output = io.StringIO()
            writer = csv.writer(output)

            # Collect dynamic headers (report fields + file labels)
            all_report_fields = []
            all_file_fields = []
            for task in tasks:
                for r in task.reports.all():
                    flat = flatten_report_data(r.data)
                    for key in flat.keys():
                        if key not in all_report_fields:
                            all_report_fields.append(key)

                    if hasattr(r, "files"):
                        for f in r.files.all():
                            if f.field_label not in all_file_fields:
                                all_file_fields.append(f.field_label)

            # Header
            header = [
                "Task ID", "Global ID", "Task Name", "Task Type",
                "Status", "Assigned Date", "Deadline",
                "Cluster", "Site", "Employee Name", "Employee Email",
                "Report ID", "Report Status", "Submitted At", "Approved At", "Rejection Reason"
            ] + all_report_fields + all_file_fields
            writer.writerow(header)

            # Rows
            for task in tasks:
                if task.reports.exists():
                    for r in task.reports.all():
                        row = [
                            task.task_id, task.global_id, task.title,
                            task.type.name if task.type else '',
                            task.status,
                            task.created_at.isoformat() if task.created_at else '',
                            task.deadline.isoformat() if task.deadline else '',
                            task.cluster.name if task.cluster else '',
                            task.site_name,
                            task.assigned_to.first_name if task.assigned_to else '',
                            task.assigned_to.email if task.assigned_to else '',
                            r.id, r.status,
                            r.submitted_at.isoformat() if r.submitted_at else '',
                            r.approved_at.isoformat() if r.approved_at else '',
                            r.rejection_reason or ''
                        ]

                        flat = flatten_report_data(r.data)
                        for f in all_report_fields:
                            row.append(flat.get(f, ""))

                        for f in all_file_fields:
                            url = ""
                            if hasattr(r, "files"):
                                match = next((ff for ff in r.files.all() if ff.field_label == f), None)
                                if match:
                                    url = request.build_absolute_uri(match.file.url)
                            row.append(url)

                        writer.writerow(row)
                else:
                    writer.writerow([
                        task.task_id, task.global_id, task.title,
                        task.type.name if task.type else '',
                        task.status,
                        task.created_at.isoformat() if task.created_at else '',
                        task.deadline.isoformat() if task.deadline else '',
                        task.cluster.name if task.cluster else '',
                        task.site_name,
                        task.assigned_to.first_name if task.assigned_to else '',
                        task.assigned_to.email if task.assigned_to else '',
                        '', '', '', '', ''
                    ] + ['' for _ in all_report_fields + all_file_fields])

            zipf.writestr(f"{group_name}.csv", output.getvalue())

    response = HttpResponse(buffer.getvalue(), content_type="application/zip")
    response['Content-Disposition'] = 'attachment; filename="tasks_export.zip"'
    return response


import io
import json
from django.db.models import Q
from django.http import HttpResponse
from django.template.loader import render_to_string
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from weasyprint import HTML
from reports.models import Report
from .models import Task
from .permissions import IsAdminOrSuperAdmin



# ======================
# Helpers
# ======================

def estimate_section_length(rows):
    """Estimate visual height of a section based on row count and value length."""
    length = 0
    for row in rows:
        value_len = len(str(row.get("value", "")))
        length += 1 + (value_len // 50)  # 1 per row + weight for long text
    return max(length, 1)


def balance_sections(sections):
    """
    Distribute sections between left and right columns, balanced by estimated length.
    sections: list of (name, rows)
    """
    weighted_sections = [
        (name, rows, estimate_section_length(rows)) for name, rows in sections
    ]

    left, right = [], []
    left_len, right_len = 0, 0

    # Place larger sections first
    for name, rows, weight in sorted(weighted_sections, key=lambda x: -x[2]):
        if left_len <= right_len:
            left.append((name, rows))
            left_len += weight
        else:
            right.append((name, rows))
            right_len += weight

    return left, right


def parse_report_data(raw_data):
    """Normalize raw report.data into a dict of sections -> rows."""
    if isinstance(raw_data, str):
        try:
            raw_data = json.loads(raw_data)
        except Exception:
            raw_data = {}

    def safe_key(s):
        return str(s).replace(" ", "_")

    form_data = {}
    if isinstance(raw_data, dict):
        is_sectioned = all(
            isinstance(v, list) and all(isinstance(item, dict) for item in v)
            for v in raw_data.values()
        )
        if is_sectioned:
            for section, rows in raw_data.items():
                form_data[safe_key(section)] = rows
        else:
            form_data["Main_Section"] = [
                {"label": k, "value": v} for k, v in raw_data.items()
            ]
    elif isinstance(raw_data, list):
        form_data["Main_Section"] = [
            {
                "label": item.get("label", ""),
                "value": item.get("answer", item.get("value", "")),
            }
            for item in raw_data
            if isinstance(item, dict)
        ]
    else:
        form_data["Main_Section"] = [{"label": "Report Data", "value": str(raw_data)}]

    # Remove duplicate labels (already in meta)
    remove_labels = [
        "Global ID",
        "Site Name",
        "Cluster",
        "Service Engineer Name",
        "Service Type",
    ]
    if "Main_Section" in form_data:
        form_data["Main_Section"] = [
            item for item in form_data["Main_Section"] if item.get("label") not in remove_labels
        ]

    if "Main Section" in form_data:
        form_data["Main_Section"] = form_data.pop("Main Section")

    return form_data


def build_report_context(request, report, task):
    task_type_name = getattr(getattr(task, "type", None), "name", "") or ""
    task_title = getattr(task, "title", "") or ""
    _, report_title = get_form_group_and_title(task_type_name or task_title)

    form_data = parse_report_data(report.data)
    sections = [(k, v) for k, v in form_data.items() if v]
    left_sections, right_sections = balance_sections(sections)

    return {
        "report_title": report_title,
        "service_type": task_title,
        "task_type": task_type_name,
        "task_id": getattr(task, "task_id", ""),
        "report_id": report.id,
        "global_id": getattr(task, "global_id", ""),
        "site_name": getattr(task, "site_name", ""),
        "cluster_name": getattr(getattr(task, "cluster", None), "name", ""),

        "employee_name": (
            getattr(task.assigned_to, "first_name", "")
            or getattr(report.submitted_by, "first_name", "")
            or "-"
        ),

        "assigned_date": format_datetime(getattr(task, "created_at", None), "N/A"),
        "planned_date": format_datetime(getattr(task, "planned_date", None), "N/A"),
        "submitted_at": format_datetime(getattr(report, "submitted_at", None), "Pending"),
        "approved_at": format_datetime(getattr(report, "approved_at", None), "Not Approved"),

        "status": getattr(report, "status", ""),
        "left_sections": left_sections,
        "right_sections": right_sections,
        "files": [
            {"label": f.field_label, "url": safe_url(request, f.file)}
            for f in getattr(report, "files", []).all()
        ] if hasattr(report, "files") else [],
        "circle": getattr(getattr(task, "assigned_by", None), "circle", ""),
        "logo_url": "/static/images/company_logo.png",

        "employee_signature": safe_url(request, getattr(getattr(report.submitted_by, "employee_profile", None), "signature_photo", None)),
        "admin_signature": safe_url(request, getattr(getattr(task.assigned_by, "employee_profile", None), "signature_photo", None)),
    }


# ======================
# Export Single Report
# ======================

@api_view(["GET"])
@permission_classes([IsAdminOrSuperAdmin])
def export_report_pdf(request, report_id):
    try:
        report = Report.objects.select_related(
            "task", "submitted_by", "submitted_by__employee_profile"
        ).prefetch_related("files").get(id=report_id)
    except Report.DoesNotExist:
        return Response({"error": "Report not found"}, status=404)

    # Role validation
    user = request.user
    if user.role == "admin":
        if report.submitted_by.circle != user.circle:
            return Response({'error': 'You cannot export reports outside your circle'}, status=403)

        emp = getattr(report.submitted_by, "employee_profile", None)
        if not emp or emp.manager_id != user.id:
            return Response({"error": "You are not the reporting manager for this employee"}, status=403)

    task = report.task
    context = build_report_context(request, report, task)

    html_string = render_to_string("report_pdf.html", context)
    pdf_file = io.BytesIO()
    HTML(string=html_string, base_url=request.build_absolute_uri("/")).write_pdf(pdf_file)
    pdf_file.seek(0)

    response = HttpResponse(pdf_file.read(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename=report_{report.id}.pdf'
    return response


# ======================
# Export Bulk Reports
# ======================

@api_view(["GET"])
@permission_classes([IsAdminOrSuperAdmin])
def export_tasks_pdf(request):
    status = request.GET.get("status")
    task_type = request.GET.get("task_type")
    search = request.GET.get("search")

    queryset = Task.objects.select_related(
        "assigned_to", "type", "cluster", "assigned_by", "site"
    ).prefetch_related("reports__files")

    if status:
        queryset = queryset.filter(status=status)
    if task_type:
        queryset = queryset.filter(title__icontains=task_type)
    if search:
        queryset = queryset.filter(
            Q(title__icontains=search)
            | Q(global_id__icontains=search)
            | Q(site_name__icontains=search)
            | Q(cluster__name__icontains=search)
            | Q(assigned_to__first_name__icontains=search)
            | Q(assigned_to__email__icontains=search)
        )

    all_html = []
    for task in queryset:
        for report in task.reports.all():
            ctx = build_report_context(request, report, task)
            all_html.append(render_to_string("report_pdf.html", ctx))

    final_html = "<div style='page-break-after: always;'></div>".join(all_html)

    pdf_file = io.BytesIO()
    HTML(string=final_html, base_url=request.build_absolute_uri("/")).write_pdf(pdf_file)
    pdf_file.seek(0)

    response = HttpResponse(pdf_file.read(), content_type="application/pdf")
    response["Content-Disposition"] = 'attachment; filename="tasks_export.pdf"'
    return response



# --- Audit Logs ---
@api_view(['GET'])
@permission_classes([IsAdminOrSuperAdmin])
def list_audit_logs(request):
    user = request.user
    logs = AuditLog.objects.select_related("user").order_by("-timestamp")

    if user.role == "admin":
        logs = logs.filter(user__circle=user.circle)


    # Apply filters
    action = request.GET.get("action")
    user_email = request.GET.get("user")
    target_type = request.GET.get("type")
    target_id = request.GET.get("id")
    date_from = request.GET.get("from")
    date_to = request.GET.get("to")

    if action:
        logs = logs.filter(action=action)
    if user_email:
        logs = logs.filter(user__email__iexact=user_email)
    if target_type:
        logs = logs.filter(target_type__iexact=target_type)
    if target_id:
        logs = logs.filter(target_id=str(target_id))
    if date_from:
        logs = logs.filter(timestamp__date__gte=date_from)
    if date_to:
        logs = logs.filter(timestamp__date__lte=date_to)

    paginator = StandardResultsSetPagination()
    page = paginator.paginate_queryset(logs, request)

    data = [{
        "id": log.id,
        "user": log.user.first_name if log.user else "System",
        "email": log.user.email if log.user else "",
        "action": log.action,
        "target_type": log.target_type,
        "target_id": log.target_id,
        "details": log.details,
        "timestamp": log.timestamp,
    } for log in page]

    return paginator.get_paginated_response(data)
