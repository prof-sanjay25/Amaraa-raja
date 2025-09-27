from __future__ import annotations
import pandas as pd
import io
from django.http import HttpResponse
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from forms.models import FormTemplate

# Task type to form group mapping
TASK_TYPE_MAPPING = {
    # DG PM variations
    'Full Services': 'dg_pm_cm',
    'Top-up': 'dg_pm_cm',
    
    # DG CM variations  
    'TOH': 'dg_pm_cm',
    'MOH': 'dg_pm_cm',
    'CM': 'dg_pm_cm',
    
    # AC variations
    'AC PM': 'ac_pm_cm',
    'AC CM': 'ac_pm_cm',
    
    # Site Visit
    'SITE VISIT': 'site_visit',
    
    # Generic fallbacks
    'DG PM': 'dg_pm_cm',
    'DG CM': 'dg_pm_cm',
}

def get_form_group_by_task_type(task_type):
    """Map task type to form group with fallback logic"""
    if not task_type:
        return 'dg_pm_cm'
    
    # Direct mapping first
    if task_type in TASK_TYPE_MAPPING:
        return TASK_TYPE_MAPPING[task_type]
    
    # Case-insensitive fallback
    task_type_lower = task_type.lower().strip()
    
    # DG related
    if any(keyword in task_type_lower for keyword in ['dg', 'generator', 'full services', 'top-up', 'toh', 'moh']):
        return 'dg_pm_cm'
    
    # AC related
    if any(keyword in task_type_lower for keyword in ['ac', 'air conditioning']):
        return 'ac_pm_cm'
        
    # Site visit related
    if any(keyword in task_type_lower for keyword in ['site', 'visit', 'inspection']):
        return 'site_visit'
    
    # Default fallback
    return 'dg_pm_cm'

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_form_by_task_type(request):
    task_type = request.GET.get('task_type')
    if not task_type:
        return Response({'error': 'task_type parameter is required'}, status=400)
    
    form_group, report_title = get_form_group_and_title(task_type)
    
    try:
        form_template = FormTemplate.objects.get(task_group=form_group)
        return Response({
            'task_type': task_type,
            'form_group': form_group,
            'report_title': report_title,
            'schema': form_template.schema,
            'total_fields': len(form_template.schema),
            'mapping_used': TASK_TYPE_MAPPING.get(task_type, 'fallback_logic')
        })
    except FormTemplate.DoesNotExist:
        return Response({
            'error': f'Form template not found for task type: {task_type} (mapped to {form_group})',
            'report_title': report_title
        }, status=404)


def get_form_group_and_title(task_type):
    """Return form group and report title based on task type"""
    if not task_type:
        return 'dg_pm_cm', 'DG Preventive Maintenance Field Service Report'
    
    # Direct dictionary match
    if task_type in TASK_TYPE_MAPPING:
        mapped_group = TASK_TYPE_MAPPING[task_type]
        if mapped_group == "dg_pm_cm":
            title = "DG Preventive Maintenance Field Service Report"
        elif mapped_group == "ac_pm_cm":
            title = "AC Preventive Maintenance Field Service Report"
        elif mapped_group == "site_visit":
            title = "Site Visit Field Service Report"
        else:
            title = "Field Service Report"
        return mapped_group, title

    
    # Case-insensitive match
    task_type_lower = task_type.lower().strip()
    
    # Corrective Maintenance
    if any(keyword in task_type_lower for keyword in ['cm', 'toh', 'moh']):
        return 'dg_pm_cm', 'DG Corrective Maintenance Field Service Report'
    
    # Preventive Maintenance
    if any(keyword in task_type_lower for keyword in ['pm', 'preventive', 'full services', 'top-up']):
        return 'dg_pm_cm', 'DG Preventive Maintenance Field Service Report'
    
    # AC related
    if 'ac' in task_type_lower or 'air conditioning' in task_type_lower:
        if 'cm' in task_type_lower:
            return 'ac_pm_cm', 'AC Corrective Maintenance Field Service Report'
        return 'ac_pm_cm', 'AC Preventive Maintenance Field Service Report'
    
    # Site visit
    if any(keyword in task_type_lower for keyword in ['site', 'visit', 'inspection']):
        return 'site_visit', 'Site Visit Field Service Report'
    
    # Default fallback → DG PM
    return 'dg_pm_cm', 'DG Preventive Maintenance Field Service Report'




@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_task_type_mappings(request):
    """Get all available task type mappings"""
    return Response({
        'mappings': TASK_TYPE_MAPPING,
        'available_form_groups': ['dg_pm_cm', 'ac_pm_cm', 'site_visit']
    })


def import_form_template(request):
    """
    Generic form template import that works for any form group
    Usage: POST with form_group parameter (dg_pm_cm, ac_pm_cm, site_visit)
    """
    file = request.FILES.get('file')
    form_group = request.data.get('form_group', 'dg_pm_cm')
    
    if not file:
        return Response({'error': 'No file provided'}, status=400)
    
    if form_group not in ['dg_pm_cm', 'ac_pm_cm', 'site_visit']:
        return Response({'error': 'Invalid form_group. Must be: dg_pm_cm, ac_pm_cm, or site_visit'}, status=400)

    filename = file.name.lower()
    schema = []

    try:
        # Load into dataframe
        if filename.endswith('.csv'):
            df = pd.read_csv(file)
        elif filename.endswith('.xlsx'):
            df = pd.read_excel(file)
        else:
            return Response({
                'error': 'Unsupported file format. Please upload a .csv or .xlsx file.'
            }, status=400)

        # Normalize column names
        df.columns = [
            c.strip().lower()
             .replace(' ', '_')
             .replace('(', '')
             .replace(')', '')
             .replace('?', '')
            for c in df.columns
        ]

        for _, row in df.iterrows():
            field_data = {}

            # Core fields with flexible column mapping
            field_data['label'] = str(row.get('question_title', row.get('label', ''))).strip()
            field_data['field_type'] = str(row.get('question_type', row.get('field_type', 'TEXT'))).strip()
            field_data['required'] = str(
                row.get('is_required', row.get('required', ''))
            ).strip().lower() in ['true', 'yes', '1', 'required']
            
            # Parse options
            options_raw = str(row.get('options_if_any', row.get('options', '')))
            field_data['options'] = [
                opt.strip() for opt in options_raw.split(',') if opt.strip() and opt.strip().lower() != 'nan'
            ]
            
            # Parse order
            field_data['order'] = (
                int(row.get('s_no', row.get('order', 0)))
                if str(row.get('s_no', row.get('order', '0'))).isdigit()
                else 0
            )

            # Generate key if not provided
            label_for_key = field_data['label'] or 'unnamed_field'
            field_data['key'] = str(
                row.get('key', label_for_key.lower().replace(' ', '_').replace('-', '_'))
            )

            # Conditional logic columns
            if_field = str(row.get('if_field', '')).strip()
            if_value = str(row.get('if_value', '')).strip()
            if (if_field and if_value and 
                if_field.lower() not in ['nan', 'null', ''] and 
                if_value.lower() not in ['nan', 'null', '']):
                field_data['if_field'] = if_field
                field_data['if_value'] = if_value

            # Include section if present
            section = str(row.get('section', '')).strip()
            if section and section.lower() not in ['nan', 'null']:
                field_data['section'] = section

            # Preserve any other columns
            for col in df.columns:
                if col not in [
                    'question_title', 'label', 'question_type', 'field_type',
                    'is_required', 'required', 'options_if_any', 'options',
                    's_no', 'order', 'key', 'if_field', 'if_value', 'section'
                ]:
                    value = row.get(col)
                    if pd.notna(value) and str(value).strip() and str(value).strip().lower() != 'nan':
                        field_data[col] = str(value).strip()

            # Only add if it has a label
            if field_data['label']:
                schema.append(field_data)

    except Exception as e:
        return Response({'error': f'Failed to parse file: {e}'}, status=400)

    if not schema:
        return Response({'error': 'No valid fields found in the uploaded file'}, status=400)

    # Replace old schema
    FormTemplate.objects.filter(task_group=form_group).delete()
    FormTemplate.objects.create(task_group=form_group, schema=schema)

    return Response({
        'message': f'{form_group.upper()} form uploaded successfully',
        'form_group': form_group,
        'fields': len(schema),
        'columns_detected': list(df.columns),
        'conditional_fields': len([f for f in schema if 'if_field' in f])
    })

# Specific import endpoints for backward compatibility
@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser])
def import_dg_pm_cm_form(request):
    request.data['form_group'] = 'dg_pm_cm'
    return import_form_template(request)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser])
def import_ac_pm_cm_form(request):
    """Import AC PM/CM form"""
    request.data['form_group'] = 'ac_pm_cm'
    return import_form_template(request)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser])
def import_site_visit_form(request):
    """Import Site Visit form"""
    request.data['form_group'] = 'site_visit'
    return import_form_template(request)

# Get endpoints
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_dg_pm_cm_form(request):
    """Get DG PM/CM form schema"""
    try:
        form_template = FormTemplate.objects.get(task_group='dg_pm_cm')
        return Response({
            'task_group': 'dg_pm_cm',
            'schema': form_template.schema,
            'total_fields': len(form_template.schema)
        })
    except FormTemplate.DoesNotExist:
        return Response({'error': 'DG PM/CM form template not found'}, status=404)



# ✅ CONFLICT RESOLUTION
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_ac_pm_cm_form(request):
    """Get AC PM/CM form schema"""
    try:
        form_template = FormTemplate.objects.get(task_group='ac_pm_cm')
        return Response({
            'task_group': 'ac_pm_cm',
            'schema': form_template.schema,
            'total_fields': len(form_template.schema)
        })
    except FormTemplate.DoesNotExist:
        return Response({'error': 'AC PM/CM form template not found'}, status=404)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_site_visit_form(request):
    """Get Site Visit form schema"""
    try:
        form_template = FormTemplate.objects.get(task_group='site_visit')
        return Response({
            'task_group': 'site_visit',
            'schema': form_template.schema,
            'total_fields': len(form_template.schema)
        })
    except FormTemplate.DoesNotExist:
        return Response({'error': 'Site Visit form template not found'}, status=404)


# --- plain helper, no decorators ---
def build_export_form_response(form_group: str):
    """Generic form export helper that returns HttpResponse"""
    try:
        form_template = FormTemplate.objects.get(task_group=form_group)

        # Debug: log schema type
        from django.http import JsonResponse
        if not isinstance(form_template.schema, (list, tuple)):
            return JsonResponse({
                "error": "Schema is not a list",
                "actual_type": str(type(form_template.schema)),
                "value": form_template.schema
            }, status=500)

        df = pd.DataFrame(form_template.schema)

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name=f'{form_group.upper()}_Form', index=False)


        output.seek(0)
        response = HttpResponse(
            output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = (
            f'attachment; filename="{form_group.upper()}_Questions.xlsx"'
        )
        return response

    except FormTemplate.DoesNotExist:
        return HttpResponse(f'{form_group} form template not found', status=404)

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        return HttpResponse(f'Failed to export form: {e}\n\n{tb}', status=500)


# --- DRF endpoints ---
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def export_dg_pm_cm_form(request):
    return build_export_form_response('dg_pm_cm')

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def export_ac_pm_cm_form(request):
    return build_export_form_response('ac_pm_cm')

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def export_site_visit_form(request):
    return build_export_form_response('site_visit')


# Site Data Import/Export with state Support - Add to superadmin/views.py


def check_superadmin_permission(user):
    """Check if user has superadmin permissions"""
    return user.is_authenticated and (user.is_superuser or getattr(user, 'role', '') == 'superadmin')

import csv, os
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from django.conf import settings
from superadmin.models import SiteData

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser])
def import_site_data(request):
    """Import site data with case-insensitive headers and state support"""
    if not check_superadmin_permission(request.user):
        return Response({'error': 'Superadmin access required'}, status=403)

    file = request.FILES.get('file')
    if not file:
        return Response({'error': 'No file provided'}, status=400)

    # Save uploaded file
    media_root = getattr(settings, 'MEDIA_ROOT', 'media')
    os.makedirs(media_root, exist_ok=True)
    saved_path = os.path.join(media_root, 'site_data.csv')
    with open(saved_path, 'wb+') as destination:
        for chunk in file.chunks():
            destination.write(chunk)

    # Decode content
    raw = open(saved_path, 'rb').read()
    try:
        decoded = raw.decode('utf-8-sig').splitlines()
    except UnicodeDecodeError:
        try:
            decoded = raw.decode('latin1').splitlines()
        except UnicodeDecodeError:
            return Response(
                {'error': 'Unable to decode file. Please save as UTF-8 or CSV again.'},
                status=400
            )

    reader = csv.DictReader(decoded)

    print("CSV Headers:", reader.fieldnames)


    # ✅ Normalize header names to lowercase


    header_map = {
        "global id": "global_id",
        "global_id": "global_id",
        "cluster name": "cluster_name",
        "cluster_name": "cluster_name",
        "site name": "site_name",
        "site_name": "site_name",
        "latitude": "latitude",
        "lat": "latitude",
        "longitude": "longitude",
        "lon": "longitude",
        "circle": "circle",
    }
    reader.fieldnames = [header_map.get(h.strip().lower(), h.strip().lower()) for h in reader.fieldnames]

    # Clear old data
    SiteData.objects.all().delete()

    circles_found = set()

    for row in reader:
        row = {k.lower(): v for k, v in row.items() if k}

        circle = row.get('circle', '')
        if circle:
            circles_found.add(circle)

        SiteData.objects.create(
            global_id=row.get('global_id', ''),
            cluster_name=row.get('cluster_name', ''),
            site_name=row.get('site_name', ''),
            latitude=row.get('latitude', ''),
            longitude=row.get('longitude', ''),
            circle=row.get('circle', ''),  # ✅ replaced state
        )

    response_data = {'message': 'Site data imported and stored (old data replaced)'}
    if circles_found:
        response_data.update({
            'circles_imported': list(circles_found),
            'total_circles': len(circles_found),
        })

    return Response(response_data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def export_site_data(request):
    """Export site data with state support"""
    if not check_superadmin_permission(request.user):
        return Response({'error': 'Superadmin access required'}, status=403)
    
    # Get export source parameter
    from_database = request.GET.get('from_database', 'false').lower() == 'true'
    
    if from_database:
        # Export from database with state field
        sites = SiteData.objects.all()
        if not sites.exists():
            return Response({'error': 'No site data found in database.'}, status=404)
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="site_data_with_states.csv"'
        
        # Include state field in CSV headers
        fieldnames = ['circle', 'global_id', 'cluster_name', 'site_name', 'latitude', 'longitude']
        writer = csv.DictWriter(response, fieldnames=fieldnames)
        writer.writeheader()

        for site in sites:
            writer.writerow({
                'circle': site.circle or '',
                'global_id': site.global_id,
                'cluster_name': site.cluster_name,
                'site_name': site.site_name,
                'latitude': site.latitude or '',
                'longitude': site.longitude or '',
            })
        
        return response
    else:
        # Export saved file (original behavior)
        media_root = getattr(settings, 'MEDIA_ROOT', 'media')
        saved_path = os.path.join(media_root, 'site_data.csv')
        if not os.path.exists(saved_path):
            return Response({'error': 'No site data file found.'}, status=404)
        with open(saved_path, 'rb') as f:
            response = HttpResponse(f.read(), content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="site_data.csv"'
            return response

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def site_data_list(request):
    """Get site data list with state information (admin + superadmin)"""
    if not (
        request.user.is_superuser or 
        getattr(request.user, 'role', '') in ['superadmin', 'admin']
    ):
        return Response({'error': 'Admin or Superadmin access required'}, status=403)

    sites = SiteData.objects.all().order_by('cluster_name', 'site_name')
    data = [
        {
            'global_id': s.global_id,
            'cluster_name': s.cluster_name,
            'site_name': s.site_name,
            'latitude': s.latitude,
            'longitude': s.longitude,
            'circle': s.circle or '',  # ✅ replaced state
        }
        for s in sites
    ]

    return Response(data)

# --- Admin Management for Superadmin ---

import os
import csv
import zipfile
import shutil
import tempfile
from datetime import datetime


from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response

from admin_panel.models import Admin
from .permissions import IsSuperAdmin

User = get_user_model()


# ----------------- Utility Helpers -----------------

def find_photo_anywhere(temp_dir, email, kind):
    """
    Search recursively for photo files by email and type (passport/signature).
    Works with or without extensions (.jpg/.jpeg/.png) and case-insensitive.
    """
    base_name = f"{email.lower()}_{kind}"
    for root, dirs, files in os.walk(temp_dir):
        for f in files:
            name, ext = os.path.splitext(f.lower())
            if name == base_name or f.lower().startswith(base_name):
                if ext in ["", ".jpg", ".jpeg", ".png"]:
                    return os.path.join(root, f)
    return None


def build_file_url(request, file_field):
    if file_field and hasattr(file_field, "url"):
        return request.build_absolute_uri(file_field.url)
    return None

# --- Admin Management APIs ---

import csv
import io
import os
import shutil
import tempfile
import zipfile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import HttpResponse
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from superadmin.permissions import IsSuperAdmin
from django.contrib.auth.password_validation import validate_password
from admin_panel.models import Admin  # ✅ adjust import path to your Admin model

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

def generate_admin_id():
    """
    Generate unique employee_id for Admins like ADM-0001, ADM-0002, ...
    """
    from admin_panel.models import Admin
    last = Admin.objects.order_by("-id").first()
    if last and last.employee_id and last.employee_id.startswith("ADM-"):
        try:
            num = int(last.employee_id.split("-")[1])
        except ValueError:
            num = last.id
        return f"ADM-{num+1:04d}"
    return "ADM-0001"



@api_view(['GET'])
@permission_classes([IsSuperAdmin])
def list_superadmins(request):
    """
    Return all superadmins (including the current user).
    """
    superadmins = User.objects.filter(role="superadmin").values(
        "id", "email", "first_name", "last_name", "is_active"
    )
    return Response(list(superadmins), status=200)


# ----------------- Create Admin -----------------

@api_view(['POST'])
@permission_classes([IsSuperAdmin])
def create_admin(request):
    # Extract fields
    name = request.data.get('name')
    email = request.data.get('email')
    password = request.data.get('password')
    confirm_password = request.data.get('confirm_password')
    circle = request.data.get('circle')
    company_name = request.data.get('company_name')
    mobile_number = request.data.get('mobile_number')
    user_type = request.data.get('user_type')
    user_role = request.data.get('user_role')
    manager_email = request.data.get('manager_email')

    passport_photo = request.FILES.get('passport_photo')
    signature_photo = request.FILES.get('signature_photo')

    # --- Validation: Required fields ---
    required_fields = {
        "name": name, "email": email, "password": password, "confirm_password": confirm_password,
        "circle": circle, "company_name": company_name, "mobile_number": mobile_number,
        "user_type": user_type, "user_role": user_role, "manager_email": manager_email,
        "passport_photo": passport_photo, "signature_photo": signature_photo,
    }
    missing = [k for k, v in required_fields.items() if not v]
    if missing:
        return Response({"error": f"Missing required fields: {', '.join(missing)}"}, status=400)

    # --- Validation: Password ---
    if password != confirm_password:
        return Response({'error': 'Passwords do not match'}, status=400)
    try:
        validate_password(password)
    except ValidationError as e:
        return Response({'error': e.messages}, status=400)

    # --- Validation: Email ---
    if User.objects.filter(email=email).exists():
        return Response({'error': 'Email already exists'}, status=400)

    # --- Validation: Mobile Number ---
    if not mobile_number.isdigit() or len(mobile_number) != 10:
        return Response({'error': 'Mobile number must be exactly 10 digits'}, status=400)

    # --- Validate manager (must be a superadmin) ---
    try:
        manager = User.objects.get(email=manager_email)
    except User.DoesNotExist:
        return Response({'error': 'Manager not found'}, status=404)

    if manager.role != "superadmin":
        return Response({'error': 'Admin must be managed by a Superadmin'}, status=400)

    # --- Create User (Admin Role) ---
    user = User.objects.create_user(
        username=email,
        email=email,
        password=password,
        first_name=name,
        circle=circle,
        role='admin',
        is_active=True
    )

    # --- Create Admin Profile ---
    admin = Admin.objects.create(
        user=user,
        employee_id=generate_admin_id(),
        company_name=company_name,
        mobile_number=mobile_number,
        passport_photo=passport_photo,
        signature_photo=signature_photo,
        user_type=user_type,
        user_role=user_role,
        manager=manager
    )

    return Response({
        'message': 'Admin created successfully',
        'user_id': user.id,
        'global_id': user.global_id,
        'state_user_id': user.state_user_id,
        'admin_id': admin.id,
        'user_type': admin.user_type,
        'user_role': admin.user_role,
    }, status=201)



# ----------------- Bulk Create Admins (ZIP) -----------------

@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser])
@permission_classes([IsSuperAdmin])
def bulk_create_admins_zip(request):
    """
    Bulk create Admins from a ZIP file containing admins.csv + photos/.
    CSV must include headers: name, email, password, confirm_password,
    circle, company_name, mobile_number, user_type, user_role, manager_email
    Photos must be named: <email>_passport(.jpg/.jpeg/.png) and <email>_signature(.jpg/.jpeg/.png)
    """
    if 'file' not in request.FILES:
        return Response({'error': 'ZIP file is required'}, status=400)

    zip_file = request.FILES['file']
    temp_dir = tempfile.mkdtemp()
    results = []

    try:
        with zipfile.ZipFile(zip_file, 'r') as z:
            z.extractall(temp_dir)

        # 🔹 Find admins.csv
        csv_path = None
        for root, _, files in os.walk(temp_dir):
            for f in files:
                if f.lower() == "admins.csv":
                    csv_path = os.path.join(root, f)
                    break
            if csv_path:
                break

        if not csv_path:
            return Response({'error': 'admins.csv not found in ZIP'}, status=400)

        with open(csv_path, newline='', encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for idx, row in enumerate(reader, start=1):
                row = {k.strip().lower(): (v.strip() if v else "") for k, v in row.items()}
                name, email = row.get('name'), row.get('email')
                password, confirm_password = row.get('password'), row.get('confirm_password')
                circle, company_name = row.get('circle'), row.get('company_name')
                mobile_number = row.get('mobile_number')
                user_type, user_role = row.get('user_type'), row.get('user_role')
                manager_email = row.get('manager_email')

                # --- Validation ---
                missing = [fld for fld in
                           ["name", "email", "password", "confirm_password", "circle",
                            "company_name", "mobile_number", "user_type", "user_role", "manager_email"]
                           if not row.get(fld)]
                if missing:
                    results.append({'row': idx, 'error': f"Missing: {', '.join(missing)}"})
                    continue

                if password != confirm_password:
                    results.append({'row': idx, 'error': 'Passwords do not match'})
                    continue

                if User.objects.filter(email=email).exists():
                    results.append({'row': idx, 'error': 'Email already exists'})
                    continue

                if not mobile_number.isdigit() or len(mobile_number) != 10:
                    results.append({'row': idx, 'error': 'Mobile must be 10 digits'})
                    continue

                try:
                    validate_password(password)
                except ValidationError as e:
                    results.append({'row': idx, 'error': e.messages})
                    continue

                # --- Validate manager ---
                try:
                    manager = User.objects.get(email=manager_email)
                except User.DoesNotExist:
                    results.append({'row': idx, 'error': f"Manager {manager_email} not found"})
                    continue

                if manager.role != "superadmin":
                    results.append({'row': idx, 'error': 'Admin must be managed by a Superadmin'})
                    continue

                # --- Create User ---
                user = User.objects.create_user(
                    username=email,
                    email=email,
                    password=password,
                    first_name=name,
                    circle=circle,
                    role='admin',
                    is_active=True
                )

                # --- Find photos ---
                passport_path = find_photo_anywhere(temp_dir, email, "passport")
                signature_path = find_photo_anywhere(temp_dir, email, "signature")

                passport_file, signature_file = None, None
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

                # --- Create Admin profile ---
                admin = Admin.objects.create(
                    user=user,
                    employee_id=generate_admin_id(),
                    company_name=company_name,
                    mobile_number=mobile_number,
                    passport_photo=passport_file,
                    signature_photo=signature_file,
                    user_type=user_type,
                    user_role=user_role,
                    manager=manager
                )

                results.append({
                    'row': idx,
                    'message': 'Admin created',
                    'email': email,
                    'user_id': user.id,
                    'admin_id': admin.id,
                    'warnings': warnings,
                })

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    success_count = len([r for r in results if r.get("message") == "Admin created"])
    error_count = len([r for r in results if "error" in r])

    if success_count == 0:
        return Response(
            {"results": results, "message": "No admins created"},
            status=400
        )
    else:
        return Response(
            {"results": results, "created": success_count, "errors": error_count},
            status=200
        )



# ----------------- Download Sample ZIP -----------------

@api_view(['GET'])
@permission_classes([IsSuperAdmin])
def download_sample_admins_zip(request):
    """Provide a sample admins.zip for reference"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        # Create sample CSV
        csv_content = io.StringIO()
        writer = csv.writer(csv_content)
        writer.writerow([
            "name", "email", "password", "confirm_password",
            "circle", "company_name", "mobile_number",
            "user_type", "user_role", "manager_email"
        ])
        writer.writerow([
            "John Doe", "john@example.com", "Password@123", "Password@123",
            "Tamil Nadu", "Acme Corp", "9876543210",
            "AREML", "Circle Head", "superadmin@example.com"
        ])
        writer.writerow([
            "Jane Smith", "jane@example.com", "Password@123", "Password@123",
            "Odisha", "Tech Pvt Ltd", "9123456789",
            "Customer", "Technician", "superadmin@example.com"
        ])
        zf.writestr("admins.csv", csv_content.getvalue())
        zf.writestr("photos/john@example.com_passport.jpg", b"sample")
        zf.writestr("photos/john@example.com_signature.jpg", b"sample")

    buffer.seek(0)
    response = HttpResponse(buffer.getvalue(), content_type="application/zip")
    response['Content-Disposition'] = 'attachment; filename=sample_admins.zip'
    return response




# ----------------- Other APIs (unchanged except cleanup) -----------------

@api_view(['POST'])
@permission_classes([IsSuperAdmin])
def toggle_admin_status(request, id):
    admin_user = get_object_or_404(User, id=id, role='admin')
    action = request.data.get('action')  # 'suspend' or 'activate'

    if action == 'suspend':
        admin_user.is_active = False
    elif action == 'activate':
        admin_user.is_active = True
    else:
        return Response({'error': 'Invalid action'}, status=400)

    admin_user.save()
    profile = getattr(admin_user, 'admin_profile', None)

    return Response({
        'status': 'success',
        'admin': {
            'id': admin_user.id,
            'name': admin_user.first_name,
            'email': admin_user.email,
            'company_name': profile.company_name if profile else '',
            'employee_id': profile.employee_id if profile else '',
            'mobile_number': profile.mobile_number if profile else '',
            'global_id': admin_user.global_id,
            'state_user_id': admin_user.state_user_id,
            'circle': admin_user.circle,
            'is_active': admin_user.is_active,
            'date_joined': admin_user.date_joined,
        }
    })


@api_view(['GET'])
@permission_classes([IsSuperAdmin])
def list_admins(request):
    admins = User.objects.filter(role='admin').order_by('-date_joined')
    data = []
    for a in admins:
        profile = getattr(a, 'admin_profile', None)
        data.append({
            'id': a.id,
            'name': a.first_name,
            'email': a.email,
            'company_name': profile.company_name if profile else '',
            'employee_id': profile.employee_id if profile else '',
            'mobile_number': profile.mobile_number if profile else '',
            'passport_photo': build_file_url(request, profile.passport_photo) if profile else None,
            'signature_photo': build_file_url(request, profile.signature_photo) if profile else None,
            'global_id': a.global_id,
            'state_user_id': a.state_user_id,
            'circle': a.circle,
            'is_active': a.is_active,
            'date_joined': a.date_joined,
        })
    return Response(data)


@api_view(['GET'])
@permission_classes([IsSuperAdmin])
def get_admin(request, id):
    admin_user = get_object_or_404(User, id=id, role='admin')
    profile = getattr(admin_user, 'admin_profile', None)
    return Response({
        'id': admin_user.id,
        'name': admin_user.first_name,
        'email': admin_user.email,
        'company_name': profile.company_name if profile else '',
        'employee_id': profile.employee_id if profile else '',
        'mobile_number': profile.mobile_number if profile else '',
        'user_type': profile.user_type if profile else '',
        'user_role': profile.user_role if profile else '',
        'manager_id': profile.manager.id if profile and profile.manager else None,
        'passport_photo': build_file_url(request, profile.passport_photo) if profile else None,
        'signature_photo': build_file_url(request, profile.signature_photo) if profile else None,
        'global_id': admin_user.global_id,
        'state_user_id': admin_user.state_user_id,
        'circle': admin_user.circle,
        'is_active': admin_user.is_active,
        'date_joined': admin_user.date_joined,
    })


@api_view(['PUT'])
@permission_classes([IsSuperAdmin])
def update_admin(request, id):
    admin_user = get_object_or_404(User, id=id, role='admin')
    profile, _ = Admin.objects.get_or_create(user=admin_user)

    admin_user.first_name = request.data.get('name', admin_user.first_name)
    admin_user.email = request.data.get('email', admin_user.email)
    if 'is_active' in request.data:
        admin_user.is_active = request.data['is_active']
    if 'circle' in request.data:
        admin_user.circle = request.data['circle']
    admin_user.save()

    if 'mobile_number' in request.data:
        mobile_number = request.data['mobile_number']
        if not mobile_number.isdigit() or len(mobile_number) != 10:
            return Response({'error': 'Mobile must be 10 digits'}, status=400)
        profile.mobile_number = mobile_number

    profile.company_name = request.data.get('company_name', profile.company_name)
    profile.user_type = request.data.get('user_type', profile.user_type)
    profile.user_role = request.data.get('user_role', profile.user_role)

    if 'manager_id' in request.data:
        try:
            manager = User.objects.get(id=int(request.data['manager_id']))
            if manager.role != "superadmin":
                return Response({'error': 'Admin must be managed by a Superadmin'}, status=400)
            profile.manager = manager
        except (User.DoesNotExist, ValueError):
            return Response({'error': 'Manager not found'}, status=404)

    if 'passport_photo' in request.FILES:
        profile.passport_photo = request.FILES['passport_photo']
    if 'signature_photo' in request.FILES:
        profile.signature_photo = request.FILES['signature_photo']

    profile.save()
    return Response({'message': 'Admin updated successfully'})


@api_view(['DELETE'])
@permission_classes([IsSuperAdmin])
def delete_admin(request, id):
    try:
        user = User.objects.get(id=id, role='admin')
        user.delete()
        return Response({'message': 'Admin deleted'})
    except User.DoesNotExist:
        return Response({'error': 'Admin not found'}, status=404)

from datetime import datetime

@api_view(['GET'])
@permission_classes([IsSuperAdmin])
def export_admins_csv(request):
    admins = User.objects.filter(role='admin')
    now = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"admin_details_{now}.csv"
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename={filename}'
    writer = csv.writer(response)
    writer.writerow([
        'Name', 'Email', 'Company Name', 'Employee ID', 'Mobile Number',
        'User Type', 'User Role', 'Manager ID', 'Circle', 'Is Active',
        'Date Joined', 'Passport Photo', 'Signature Photo'
    ])
    for a in admins:
        profile = getattr(a, 'admin_profile', None)
        writer.writerow([
            a.first_name, a.email,
            profile.company_name if profile else '',
            profile.employee_id if profile else '',
            profile.mobile_number if profile else '',
            profile.user_type if profile else '',
            profile.user_role if profile else '',
            profile.manager.id if profile and profile.manager else '',
            a.circle,
            'Active' if a.is_active else 'Suspended',
            a.date_joined.strftime("%Y-%m-%d %H:%M:%S"),
            build_file_url(request, profile.passport_photo) if profile else '',
            build_file_url(request, profile.signature_photo) if profile else '',
        ])
    return response



# --- 5. Employee Management ---

from rest_framework.decorators import api_view, permission_classes


from rest_framework.response import Response
from django.contrib.auth import get_user_model
from employees.models import Employee
from django.core.exceptions import ValidationError

User = get_user_model()

@api_view(['POST'])
@permission_classes([IsSuperAdmin])
def create_employee(request):
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
    circle = request.data.get('circle')   # 🔹 new

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
    if not circle: missing.append("circle")   # 🔹 ensure circle given

    if missing:
        return Response({"error": f"Missing required fields: {', '.join(missing)}"}, status=400)

    # --- Validate circle ---
    valid_circles = [c[0] for c in User.CIRCLE_CHOICES]
    if circle not in valid_circles:
        return Response({"error": f"Invalid circle. Must be one of {valid_circles}"}, status=400)

    # --- Password validation ---
    if password != confirm_password:
        return Response({'error': 'Passwords do not match'}, status=400)

    try:
        User.validate_password_strength(password)
    except ValidationError as e:
        return Response({'error': str(e)}, status=400)

    if User.objects.filter(email=email).exists():
        return Response({'error': 'Email already exists'}, status=400)

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
        username=email,   # 🔹 safer unique username
        email=email,
        password=password,
        first_name=name,
        circle=circle,    # 🔹 use selected circle
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
        'circle': user.circle,
    }, status=201)




import zipfile, tempfile, os, csv
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.decorators import api_view, permission_classes, parser_classes


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
@permission_classes([IsSuperAdmin])
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
            circle = row.get('circle')

            # --- Validation ---
            missing = []
            for field, label in [
                (name, "name"), (email, "email"),
                (password, "password"), (confirm_password, "confirm_password"),
                (company_name, "company_name"), (employee_id, "employee_id"),
                (mobile_number, "mobile_number"),
                (user_type, "user_type"), (user_role, "user_role"),
                (manager_email, "manager_email"), (circle, "circle"),
            ]:
                if not field:
                    missing.append(label)
            if missing:
                results.append({'row': idx, 'error': f"Missing required fields: {', '.join(missing)}"})
                continue

            # --- Validate circle ---
            valid_circles = [c[0] for c in User.CIRCLE_CHOICES]
            if circle not in valid_circles:
                results.append({'row': idx, 'error': f"Invalid circle {circle}. Must be one of {valid_circles}"})
                continue

            # --- Create User ---
            user = User.objects.create_user(
                username=email,
                email=email,
                password=password,
                first_name=name,
                circle=circle,   # 🔹 use provided circle
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

            # --- Resolve Manager ---
            manager = None
            if manager_email:
                try:
                    manager = User.objects.get(email=manager_email)
                except User.DoesNotExist:
                    results.append({'row': idx, 'error': f"Manager with email {manager_email} not found"})
                    continue

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
from .permissions import IsSuperAdmin

@api_view(['GET'])
@permission_classes([IsSuperAdmin])
def bulk_employee_sample_zip(request):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        # --- employees.csv ---
        csv_buffer = io.StringIO()
        writer = csv.writer(csv_buffer)
        writer.writerow([
            "name", "email", "password", "confirm_password",
            "company_name", "employee_id", "mobile_number",
            "user_type", "user_role", "manager_email", "circle"
        ])
        writer.writerow([
            "John Doe", "john@example.com", "Pass@123", "Pass@123",
            "AREML Pvt Ltd", "EMP001", "9876543210",
            "AREML", "Technician", "admin@example.com", "Tamil Nadu"
        ])
        writer.writerow([
            "Jane Smith", "jane@example.com", "Pass@123", "Pass@123",
            "SWEAR Solutions", "EMP002", "9123456789",
            "SWEAR", "Supervisor", "admin@example.com", "Odisha"
        ])
        zf.writestr("employees.csv", csv_buffer.getvalue())

        # --- Add VALID small JPEG bytes ---
        minimal_jpeg = (
            b"\xFF\xD8"              # SOI
            b"\xFF\xE0"              # APP0 marker
            b"\x00\x10"              # length
            b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
            b"\xFF\xD9"              # EOI
        )
        zf.writestr("photos/john@example.com_passport.jpg", minimal_jpeg)
        zf.writestr("photos/john@example.com_signature.jpg", minimal_jpeg)
        zf.writestr("photos/jane@example.com_passport.jpg", minimal_jpeg)
        zf.writestr("photos/jane@example.com_signature.jpg", minimal_jpeg)

    buffer.seek(0)
    response = HttpResponse(buffer.getvalue(), content_type="application/zip")
    response['Content-Disposition'] = 'attachment; filename=employee_bulk_template.zip'
    return response





# --- 5. Employee Management ---

from django.shortcuts import get_object_or_404

@api_view(['POST'])
@permission_classes([IsSuperAdmin])
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
@permission_classes([IsSuperAdmin])
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
@permission_classes([IsSuperAdmin])
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
@permission_classes([IsSuperAdmin])
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
@permission_classes([IsSuperAdmin])
def delete_employee(request, id):
    try:
        user = User.objects.get(id=id, role='employee')
        user.delete()
        return Response({'message': 'Employee deleted'})
    except User.DoesNotExist:
        return Response({'error': 'Employee not found'}, status=404)


from datetime import datetime


@api_view(['GET'])
@permission_classes([IsSuperAdmin])
def export_employees_csv(request):
    user = request.user

    employees = User.objects.filter(role='employee')

    # 🔹 Restrict Admins to their state only
    if user.role == "admin":
        employees = employees.filter(circle=user.circle)


    # 🔹 Always generate unique filename with timestamp
    now = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
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





# --- Superadmin Task & Report Management ---

from rest_framework.decorators import api_view, permission_classes


from rest_framework.response import Response
from admin_panel.models import Task
from admin_panel.pagination import StandardResultsSetPagination

@api_view(['GET'])
@permission_classes([IsSuperAdmin])
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
@permission_classes([IsSuperAdmin])
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
@permission_classes([IsSuperAdmin])
def list_reports(request):
    user = request.user

    reports = Report.objects.select_related(
        'task',
        'submitted_by',
        'submitted_by__employee_profile',
        'task__cluster',
        'task__assigned_by'
    ).order_by('-submitted_at')

   

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




from admin_panel.audit import log_action  # import the helper we made

@api_view(['POST'])
@permission_classes([IsSuperAdmin])
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







# --- View Report ---
from django.utils.dateformat import format

@api_view(['GET'])
@permission_classes([IsSuperAdmin])
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




import io
import csv
import json
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils.timezone import localtime
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from weasyprint import HTML


from reports.models import Report
from admin_panel.models import AuditLog
from admin_panel.pagination import StandardResultsSetPagination


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
@permission_classes([IsSuperAdmin])
def export_report_csv(request, report_id):
    try:
        report = Report.objects.select_related(
            'task', 'submitted_by', 'submitted_by__employee_profile'
        ).prefetch_related('files').get(id=report_id)
    except Report.DoesNotExist:
        return Response({'error': 'Report not found'}, status=404)

    user = request.user
    

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
@permission_classes([IsSuperAdmin])
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
from admin_panel.models import Task




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
@permission_classes([IsSuperAdmin])
def export_report_pdf(request, report_id):
    try:
        report = Report.objects.select_related(
            "task", "submitted_by", "submitted_by__employee_profile"
        ).prefetch_related("files").get(id=report_id)
    except Report.DoesNotExist:
        return Response({"error": "Report not found"}, status=404)

    # Role validation
    user = request.user
    

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
@permission_classes([IsSuperAdmin])
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
@permission_classes([IsSuperAdmin])
def list_audit_logs(request):
    user = request.user
    logs = AuditLog.objects.select_related("user").order_by("-timestamp")

    


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








# superadmin/views.py  — Production Dashboard (refactored)


from datetime import datetime, date
import calendar
import csv
from typing import Dict, Tuple

from django.contrib.auth import get_user_model
from django.db import connection
from django.db.models import (
    Count, Q, Case, When, CharField, Value, QuerySet, DateField, F
)
from django.db.models.functions import TruncMonth, TruncDate, Coalesce, Cast
from django.http import HttpResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from admin_panel.models import Task, TaskType, AuditLog
from reports.models import Report  # noqa  (prefetch safety)
from superadmin.models import SiteData
from .permissions import IsSuperAdmin  # keep your original permission

User = get_user_model()


# =========================
# Helpers (single source of truth)
# =========================

CATEGORY_KEYS = {
    "DG PM": ["full services", "top-up"],
    "DG CM": ["toh", "moh", "cm"],
    "AC PM": ["ac pm"],
    "AC CM": ["ac cm"],
    "Site Visit": ["site visit"],
}


ALL_STATUSES = {"pending", "wait_for_review", "completed", "overdue"}  # model may or may not have 'overdue'


def categorize_task_name(task_type_name: str | None) -> str:
    """Pure-Python fallback for CSV/export/etc."""
    name = (task_type_name or "Other").strip().lower()
    for cat, needles in CATEGORY_KEYS.items():
        if any(n in name for n in needles):
            return cat
    return "Other"


def annotate_task_category(qs: QuerySet[Task]) -> QuerySet[Task]:
    """DB-side annotation for category (kept consistent with categorize_task_name)."""
    # Build When() blocks from CATEGORY_KEYS
    whens = []
    for cat, needles in CATEGORY_KEYS.items():
        q = Q()
        for n in needles:
            q |= Q(type__name__icontains=n)
        whens.append(When(q, then=Value(cat)))

    return qs.annotate(
        task_category=Case(
            *whens,
            default=Coalesce(F("type__name"), Value("Other")),
            output_field=CharField(),
        )
    )


def parse_filters(request) -> Tuple[dict, dict]:
    raw = {
        "from_date": request.GET.get("from_date"),
        "to_date": request.GET.get("to_date"),
        "username": (request.GET.get("username") or "").strip(),
        "circle": (request.GET.get("circle") or "").strip(),
        "cluster": (request.GET.get("cluster") or "").strip(),
        "site": (request.GET.get("site") or "").strip(),
        "task_type": request.GET.get("task_type"),
        "task_category": request.GET.get("task_category"),  # UI only
    }

    dj = {}

    # Date range
    if raw["from_date"] and raw["to_date"]:
        try:
            f = datetime.strptime(raw["from_date"], "%Y-%m-%d").date()
            t = datetime.strptime(raw["to_date"], "%Y-%m-%d").date()
            dj["planned_date__range"] = (f, t)
        except ValueError:
            pass

    # Username
    if raw["username"]:
        dj["username_q"] = Q(
            Q(assigned_to__username__icontains=raw["username"]) |
            Q(assigned_to__first_name__icontains=raw["username"]) |
            Q(assigned_to__email__icontains=raw["username"])
        )

    # Circle
    if raw["circle"]:
        site_names = SiteData.objects.filter(circle__iexact=raw["circle"]).values_list("site_name", flat=True)
        dj["circle_q"] = Q(site__circle__iexact=raw["circle"]) | Q(site_name__in=site_names)

    # Cluster
    if raw["cluster"]:
        dj["cluster_q"] = Q(cluster__name__icontains=raw["cluster"]) | Q(site__cluster_name__icontains=raw["cluster"])

    # Site
    if raw["site"]:
        dj["site_q"] = Q(site__site_name__icontains=raw["site"]) | Q(site_name__icontains=raw["site"])

    # ✅ Task Type (individual)
    if raw["task_type"]:
        dj["task_type_q"] = Q(type__name__iexact=raw["task_type"])

    # ⚠️ Task Category will be used only in frontend (for grouping)
    return raw, dj



def apply_filters(qs: QuerySet[Task], dj_filters: dict) -> QuerySet[Task]:
    if "planned_date__range" in dj_filters:
        qs = qs.filter(planned_date__range=dj_filters["planned_date__range"])
    if "username_q" in dj_filters:
        qs = qs.filter(dj_filters["username_q"])
    if "circle_q" in dj_filters:
        qs = qs.filter(dj_filters["circle_q"])
    if "cluster_q" in dj_filters:
        qs = qs.filter(dj_filters["cluster_q"])
    if "site_q" in dj_filters:
        qs = qs.filter(dj_filters["site_q"])
    if "task_type_q" in dj_filters:
        qs = qs.filter(dj_filters["task_type_q"])
    return qs




def compute_overdue_counts(base_qs: QuerySet[Task]) -> int:
    """
    If model has explicit 'overdue' status, use it.
    Otherwise compute: planned_date < today AND status != completed.
    """
    today = date.today()
    if "overdue" in ALL_STATUSES:
        try:
            return base_qs.filter(status="overdue").count()
        except Exception:
            pass
    return base_qs.filter(
        planned_date__lt=today
    ).exclude(status="completed").count()


def date_trends(qs_annotated: QuerySet[Task]) -> list[dict]:
    """Date-wise trend (SQLite-compatible)."""
    if connection.vendor == "sqlite":
        raw = (
            qs_annotated.filter(planned_date__isnull=False)
            .annotate(month=TruncMonth("planned_date"))
            .values("month", "task_category", "status")
            .annotate(count=Count("id"))
            .order_by("month", "task_category")
        )
        out = []
        for r in raw:
            d = r.get("date_only")
            if d:
                out.append({
                    "date": d,
                    "task_category": r["task_category"],
                    "status": r["status"],
                    "count": r["count"],
                })
        return out

    # Other DBs
    raw = (
        qs_annotated.filter(planned_date__isnull=False)
        .annotate(date=TruncDate("planned_date"))
        .values("date", "task_category", "status")
        .annotate(count=Count("id"))
        .order_by("date", "task_category")
    )
    return [{
        "date": item["date"].isoformat(),
        "task_category": item["task_category"],
        "status": item["status"],
        "count": item["count"],
    } for item in raw]


def month_trends(qs_annotated: QuerySet[Task]) -> list[dict]:
    """Month-wise trend (SQLite-compatible)."""
    if connection.vendor == "sqlite":
        raw = (
            qs_annotated.filter(planned_date__isnull=False)
            .extra(select={"month_only": "strftime('%%Y-%%m-01', planned_date)"})
            .values("month_only", "task_category", "status")
            .annotate(count=Count("id"))
            .order_by("month_only", "task_category")
        )
        out = []
        for r in raw:
            m = r.get("month_only")
            if not m:
                continue
            dtm = datetime.strptime(m, "%Y-%m-%d").date()
            out.append({
                "month": dtm.isoformat(),
                "month_name": calendar.month_name[dtm.month],
                "year": dtm.year,
                "task_category": r["task_category"],
                "status": r["status"],
                "count": r["count"],
            })
        return out

    raw = (
        qs_annotated.filter(planned_date__isnull=False)
        .annotate(month=TruncMonth("planned_date"))
        .values("month", "task_category", "status")
        .annotate(count=Count("id"))
        .order_by("month", "task_category")
    )
    return [{
        "month": item["month"].isoformat(),
        "month_name": calendar.month_name[item["month"].month],
        "year": item["month"].year,
        "task_category": item["task_category"],
        "status": item["status"],
        "count": item["count"],
    } for item in raw]


def pie_from_category_stats(qs_annotated: QuerySet[Task]) -> list[dict]:
    """Build pie chart dataset with completion % per category."""
    agg = (
        qs_annotated
        .values("task_category", "status")
        .annotate(count=Count("id"))
        .order_by("task_category", "status")
    )
    bucket: Dict[str, Dict[str, int]] = {}
    for row in agg:
        cat = row["task_category"]
        status = row["status"]
        count = row["count"]
        if cat not in bucket:
            bucket[cat] = {s: 0 for s in ["pending", "wait_for_review", "completed", "overdue"]}
            bucket[cat]["total"] = 0
        bucket[cat]["total"] += count
        if status in bucket[cat]:
            bucket[cat][status] += count

    out = []
    for cat, data in bucket.items():
        total = data["total"] or 0
        completed = data.get("completed", 0)
        out.append({
            "category": cat,
            "total": total,
            "completed": completed,
            "pending": data.get("pending", 0),
            "wait_for_review": data.get("wait_for_review", 0),
            "overdue": data.get("overdue", 0),
            "completion_percentage": round((completed / total) * 100, 1) if total > 0 else 0.0,
        })
    return out


def user_perf(qs_annotated: QuerySet[Task]) -> list[dict]:
    raw = (
        qs_annotated
        .values(
            "assigned_to__username",
            "assigned_to__first_name",
            "assigned_to__email",
            "task_category",
            "status",
        )
        .annotate(count=Count("id"))
        .order_by("assigned_to__username", "task_category")
    )
    return [{
        "username": r["assigned_to__username"],
        "name": r["assigned_to__first_name"],
        "email": r["assigned_to__email"],
        "category": r["task_category"],
        "status": r["status"],
        "count": r["count"],
    } for r in raw if r["assigned_to__username"]]


def circle_rollup(qs: QuerySet[Task], show_all: bool, selected_circle: str) -> list[dict]:
    """
    Fast rollup by related site.circle.
    If a circle filter is active, skip global roll-up to avoid redundant data.
    """
    if not show_all and selected_circle:
        return []

    # Only aggregate where site has a circle; tasks that only store site_name and no site FK
    # cannot be attributed here without a subquery join, which is expensive per-row. Keep it fast.
    agg = (
        qs.exclude(site__circle__isnull=True)
          .exclude(site__circle__exact="")
          .values("site__circle")
          .annotate(
              total=Count("id"),
              completed=Count("id", filter=Q(status="completed")),
              pending=Count("id", filter=Q(status="pending")),
              wait_for_review=Count("id", filter=Q(status="wait_for_review")),
              overdue=Count("id", filter=Q(status="overdue")) if "overdue" in ALL_STATUSES else Value(0),
          )
          .order_by("site__circle")
    )
    out = []
    for r in agg:
        total = r["total"]
        completed = r["completed"]
        out.append({
            "circle": r["site__circle"],
            "total_tasks": total,
            "completed": completed,
            "pending": r["pending"],
            "wait_for_review": r["wait_for_review"],
            "overdue": r.get("overdue", 0),
            "completion_rate": round((completed / total) * 100, 1) if total > 0 else 0.0,
        })
    return out


def cluster_rollup(qs: QuerySet[Task]) -> list[dict]:
    agg = (
        qs.exclude(cluster__name__isnull=True)
          .exclude(cluster__name__exact="")
          .values("cluster__name")
          .annotate(
              total=Count("id"),
              completed=Count("id", filter=Q(status="completed")),
              pending=Count("id", filter=Q(status="pending")),
              wait_for_review=Count("id", filter=Q(status="wait_for_review")),
              overdue=Count("id", filter=Q(status="overdue")) if "overdue" in ALL_STATUSES else Value(0),
          )
          .order_by("-total")
    )
    out = []
    for r in agg:
        total = r["total"]
        completed = r["completed"]
        out.append({
            "cluster": r["cluster__name"],
            "total": total,
            "completed": completed,
            "pending": r["pending"],
            "wait_for_review": r["wait_for_review"],
            "overdue": r.get("overdue", 0),
            "completion_rate": round((completed / total) * 100, 1) if total > 0 else 0.0,
        })
    return out


# =========================
# Endpoints
# =========================

@api_view(["GET"])
@permission_classes([IsSuperAdmin])
def dashboard_analytics(request):
    """
    Production dashboard endpoint (single source of truth):
    - Unified filters, categorization and aggregations
    - Cross-DB date & month trends
    - Includes audit logs
    """
    # Base queryset + joins
    base_qs = Task.objects.select_related("type", "assigned_to", "site", "cluster").prefetch_related("reports")

    # Parse & apply filters
    raw_filters, dj_filters = parse_filters(request)
    base_qs = apply_filters(base_qs, dj_filters)

    # Annotate category once, reuse everywhere
    qs_cat = annotate_task_category(base_qs)

    # Task category filter (after annotation)
    if raw_filters["task_category"]:
        qs_cat = qs_cat.filter(task_category=raw_filters["task_category"])


    # Summary (use qs_cat, not base_qs)
    total_tasks = qs_cat.count()
    summary = {
        "total_tasks": total_tasks,
        "completed_tasks": qs_cat.filter(status="completed").count(),
        "pending_tasks": qs_cat.filter(status="pending").count(),
        "wait_for_review_tasks": qs_cat.filter(status="wait_for_review").count(),
        "overdue_tasks": compute_overdue_counts(qs_cat),
    }
    summary["completion_rate"] = (
        round((summary["completed_tasks"] / total_tasks) * 100, 2)
        if total_tasks else 0.0
    )

    # Charts & Trends
    pie_chart = pie_from_category_stats(qs_cat)
    date_trend = date_trends(qs_cat)
    month_trend = month_trends(qs_cat)

    # Performance
    performance = user_perf(qs_cat)

    # Rollups (also filter by category!)
    circles = circle_rollup(qs_cat, show_all=not bool(raw_filters["circle"]), selected_circle=raw_filters["circle"])
    clusters = cluster_rollup(qs_cat)

    # Recent audit logs (last 30)
    audit_logs = list(
        AuditLog.objects.order_by("-timestamp")[:30]
        .values("user__username", "action", "timestamp")
    )

    # Filter options for UI
    filter_options = {
        "users": list(
            User.objects.filter(role__in=["admin", "employee"], is_active=True)
            .values("username", "first_name", "email")
            .order_by("username")
        ),
        "circle": list(
            SiteData.objects.exclude(circle__isnull=True).exclude(circle__exact="")
            .values_list("circle", flat=True).distinct().order_by("circle")
        ),
        "clusters": list(
            SiteData.objects.exclude(cluster_name__isnull=True).exclude(cluster_name__exact="")
            .values_list("cluster_name", flat=True).distinct().order_by("cluster_name")
        ),
        "task_types": list(TaskType.objects.values("id", "name").order_by("name")),
        "task_categories": [
            {"value": "DG PM", "label": "DG PM (Full Services, Top-up)"},
            {"value": "DG CM", "label": "DG CM (TOH, MOH, CM)"},
            {"value": "AC PM", "label": "AC PM"},
            {"value": "AC CM", "label": "AC CM"},
            {"value": "Site Visit", "label": "Site Visit"},
            {"value": "Other", "label": "Other"},
        ],
    }

    return Response({
        "summary": summary,
        "filters_applied": raw_filters,
        "pie_chart": pie_chart,
        "date_wise_trends": date_trend,
        "month_wise_trends": month_trend,
        "user_performance": performance,
        "circle_analysis": circles,
        "cluster_analysis": clusters,
        "audit_logs": audit_logs,
        "filter_options": filter_options,
    })


@api_view(["GET"])
@permission_classes([IsSuperAdmin])
def dashboard_export(request):
    """
    CSV export aligned 1:1 with the production dashboard (same filters & categorization).
    """
    base_qs = Task.objects.select_related("type", "assigned_to", "site", "cluster")
    _, dj_filters = parse_filters(request)
    base_qs = apply_filters(base_qs, dj_filters)

    # Stream response
    response = HttpResponse(content_type="text/csv")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    response["Content-Disposition"] = f'attachment; filename="dashboard_export_{timestamp}.csv"'
    writer = csv.writer(response)

    writer.writerow([
        "Task ID", "Global ID", "Task Type", "Category", "Status",
        "Assigned To", "User Email", "Planned Date", "Created Date",
        "Circle", "Cluster", "Site Name", "Completion Status"
    ])

    for task in base_qs.iterator():
        task_type_name = task.type.name if task.type else "Other"
        category = categorize_task_name(task_type_name)
        planned = task.planned_date.isoformat() if task.planned_date else ""
        created = task.created_at.isoformat() if getattr(task, "created_at", None) else ""
        circle = getattr(task.site, "circle", "") if task.site else ""
        cluster = task.cluster.name if task.cluster else ""
        site_name = task.site_name or (task.site.site_name if task.site else "")

        writer.writerow([
            getattr(task, "task_id", task.id),
            getattr(task, "global_id", ""),
            task_type_name,
            category,
            task.status,
            task.assigned_to.username if task.assigned_to else "Unassigned",
            task.assigned_to.email if task.assigned_to else "",
            planned,
            created,
            circle,
            cluster,
            site_name,
            "Completed" if task.status == "completed" else "Not Completed",
        ])

    return response


@api_view(["GET"])
@permission_classes([IsSuperAdmin])
def get_task_categories(request):
    """Static task categories for filters (kept in sync with CATEGORY_KEYS)."""
    categories = [
        {"value": "DG PM", "label": "DG PM (Full Services, Top-up)"},
        {"value": "DG CM", "label": "DG CM (TOH, MOH, CM)"},
        {"value": "AC PM", "label": "AC PM"},
        {"value": "AC CM", "label": "AC CM"},
        {"value": "Site Visit", "label": "Site Visit"},
        {"value": "Other", "label": "Other"},
    ]
    return Response({"categories": categories, "total_categories": len(categories)})


@api_view(["GET"])
@permission_classes([IsSuperAdmin])
def get_filter_options(request):
    """Filter options for UI with category → types mapping."""
    users = User.objects.filter(role__in=["admin", "employee"], is_active=True) \
        .values("id", "username", "first_name", "email").order_by("username")

    circles = SiteData.objects.exclude(
        Q(circle__isnull=True) | Q(circle__exact="")
    ).values_list("circle", flat=True).distinct().order_by("circle")

    clusters = SiteData.objects.exclude(
        Q(cluster_name__isnull=True) | Q(cluster_name__exact="")
    ).values_list("cluster_name", flat=True).distinct().order_by("cluster_name")

    # Grouped Task Types
    task_types = []
    for category, types in CATEGORY_KEYS.items():
        task_types.append({
            "category": category,
            "types": [{"value": t, "label": t} for t in types]
        })

    return Response({
        "users": list(users),
        "circles": list(circles),
        "clusters": list(clusters),
        "task_types_grouped": task_types,  # 👈 use this in frontend
    })




@api_view(['GET', 'PUT'])
@permission_classes([IsSuperAdmin])
def superadmin_profile(request):
    superadmin_user = request.user

    if superadmin_user.role != "superadmin":
        return Response({"error": "Only superadmins can access this endpoint"}, status=403)

    if request.method == "GET":
        def build_url(file_field):
            if file_field and hasattr(file_field, "url"):
                return request.build_absolute_uri(file_field.url)
            return None

        data = {
            "id": superadmin_user.id,
            "fullName": superadmin_user.first_name or superadmin_user.username,
            "email": superadmin_user.email,
            "role": superadmin_user.role,
            "global_id": superadmin_user.global_id,
            "state_user_id": superadmin_user.state_user_id,
            "circle": superadmin_user.circle,
            "is_active": superadmin_user.is_active,
            "date_joined": superadmin_user.date_joined,
            "passport_photo": build_url(superadmin_user.passport_photo),
            "signature_photo": build_url(superadmin_user.signature_photo),
        }
        return Response(data)

    elif request.method == "PUT":
        name = request.data.get("fullName")
        if name:
            superadmin_user.first_name = name
        if "circle" in request.data:
            superadmin_user.circle = request.data["circle"]
        if "is_active" in request.data:
            superadmin_user.is_active = request.data["is_active"]

        if "passport_photo" in request.FILES:
            superadmin_user.passport_photo = request.FILES["passport_photo"]
        if "signature_photo" in request.FILES:
            superadmin_user.signature_photo = request.FILES["signature_photo"]

        superadmin_user.save()
        return Response({"message": "Superadmin profile updated successfully"})


# --- Change Password ---
from django.core.exceptions import ValidationError

@api_view(['POST'])
@permission_classes([IsSuperAdmin])
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