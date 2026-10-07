"""Account management rules: creation, roles, activation, passwords and session revocation."""

from django.db import transaction
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.api import ConflictError

from .models import Role, User


def revoke_all_sessions(user):
    """Blacklist every refresh token of `user`: nobody can renew a session after this."""
    for token in OutstandingToken.objects.filter(user=user):
        BlacklistedToken.objects.get_or_create(token=token)


def create_user_account(**data):
    return User.objects.create_user(**data)


def update_user(user_id, *, actor, changes):
    """Apply profile, role and activation changes without ever leaving the app without an admin.

    Every active admin row is locked first (always in primary-key order), so two admins who
    demote each other at the same instant are serialised and the second one is refused."""
    with transaction.atomic():
        admins = list(
            User.objects.select_for_update()
            .filter(role=Role.ADMIN, is_active=True)
            .order_by("pk")
        )
        user = User.objects.select_for_update().get(pk=user_id)
        new_role = changes.get("role", user.role)
        new_active = changes.get("is_active", user.is_active)

        loses_admin_access = (
            user.role == Role.ADMIN
            and user.is_active
            and (new_role != Role.ADMIN or not new_active)
        )
        if loses_admin_access:
            if user.pk == actor.pk:
                raise ConflictError("You cannot remove your own administrator access.")
            if not [admin for admin in admins if admin.pk != user.pk]:
                raise ConflictError("The last active administrator cannot be demoted or deactivated.")

        was_active = user.is_active
        for field, value in changes.items():
            setattr(user, field, value)
        user.save(update_fields=[*changes, "updated_at"])
        if was_active and not new_active:
            revoke_all_sessions(user)
    return user


def set_user_password(user_id, password):
    """Administrator reset: also signs the user out everywhere."""
    with transaction.atomic():
        user = User.objects.select_for_update().get(pk=user_id)
        user.set_password(password)
        user.save(update_fields=["password", "updated_at"])
        revoke_all_sessions(user)
    return user


def change_own_password(user, new_password):
    """Change the caller's password, sign out every other session and return fresh tokens."""
    user.set_password(new_password)
    user.save(update_fields=["password", "updated_at"])
    revoke_all_sessions(user)
    refresh = RefreshToken.for_user(user)
    return {"access": str(refresh.access_token), "refresh": str(refresh)}