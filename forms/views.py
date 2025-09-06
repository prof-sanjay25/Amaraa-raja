import csv
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser
from .models import FormTemplate

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser])
def upload_form_template(request):
    group = request.GET.get('group')  # expected: dg, ac, site_visit
    file = request.FILES.get('file')

    if not group or group not in ['dg', 'ac', 'site_visit']:
        return Response({'error': 'Invalid task group'}, status=400)
    if not file:
        return Response({'error': 'CSV file required'}, status=400)

    decoded_file = file.read().decode('utf-8-sig').splitlines()
    reader = csv.DictReader(decoded_file)

    schema = []
    for row in reader:
        schema.append({
            'label': row['label'].strip(),
            'field_type': row['field_type'].strip(),
            'required': row['required'].strip().lower() == 'true',
            'options': [opt.strip() for opt in row.get('options', '').split(',') if opt.strip()],
            'order': int(row['order']) if row['order'].isdigit() else 0,
        })

    FormTemplate.objects.update_or_create(
        task_group=group,
        defaults={'schema': schema}
    )

    return Response({'message': f'{group} form uploaded', 'fields': len(schema)})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_form_template(request):
    """
    Get form template by task_group (dg, ac, site_visit).
    Example: /forms/get_form_template/?task_group=dg
    """
    task_group = request.GET.get('task_group', '').strip().lower()

    if task_group not in ['dg', 'ac', 'site_visit']:
        return Response({'error': 'Invalid or missing task_group'}, status=400)

    template = FormTemplate.objects.filter(task_group=task_group).first()
    if not template:
        return Response({'error': 'Template not found'}, status=404)

    return Response({'schema': template.schema})

