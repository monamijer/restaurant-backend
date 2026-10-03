"""Role-based permissions. The role is read from the database on every request, so
demoting a user takes effect immediately instead of when their token expires."""

from rest_framework.permissions import SAFE_METHODS, BasePermission

from .models import Role

STAFF_ROLES = (Role.STAFF, Role.ADMIN)
ADMIN_ROLES = (Role.ADMIN,)


def _has_role(request, roles):
    user = request.user
    return bool(user and user.is_authenticated and user.role in roles)


class IsStaffRole(BasePermission):
    """Restaurant staff or administrators."""

    def has_permission(self, request, view):
        return _has_role(request, STAFF_ROLES)


class IsAdminRole(BasePermission):
    def has_permission(self, request, view):
        return _has_role(request, ADMIN_ROLES)


class IsAdminOrReadOnly(BasePermission):
    """Anyone may read; only administrators may write."""

    def has_permission(self, request, view):
        return request.method in SAFE_METHODS or _has_role(request, ADMIN_ROLES)