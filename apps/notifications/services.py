"""Single entry point for creating notifications, so every module words them the same way."""

from apps.accounts.models import Role, User

from .models import Notification

STAFF_ROLES = (Role.STAFF, Role.ADMIN)


def notify(user, notification_type, message):
    return Notification.objects.create(user=user, type=notification_type, message=message)


def notify_staff(notification_type, message):
    """One notification per active staff member and administrator."""
    recipients = User.objects.filter(role__in=STAFF_ROLES, is_active=True)
    Notification.objects.bulk_create(
        [Notification(user=user, type=notification_type, message=message) for user in recipients]
    )