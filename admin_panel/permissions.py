from rest_framework.permissions import BasePermission

class IsAdminOrSuperAdmin(BasePermission):
    """
    Custom permission: Allow only Admin or Superadmin users.
    """
    ALLOWED_ROLES = {"admin", "superadmin"}

    def has_permission(self, request, view):
        role = getattr(request.user, "role", "").lower()
        return request.user and request.user.is_authenticated and role in self.ALLOWED_ROLES
