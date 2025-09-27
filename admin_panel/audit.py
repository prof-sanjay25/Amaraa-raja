from admin_panel.models import AuditLog

def log_action(user, action, target_type, target_id, details=None):
    AuditLog.objects.create(
        user=user,
        action=action,
        target_type=target_type,
        target_id=str(target_id),
        details=details or {}
    )
