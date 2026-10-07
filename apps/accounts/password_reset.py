"""Password reset by e-mail: a signed, expiring, single-use link.

Django's token generator ties a token to the user's current password hash and last login, so a
link stops working when the password changes (single use), when the user signs in, or when
PASSWORD_RESET_TIMEOUT elapses. The request step never reveals whether an address exists."""

import logging

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework.exceptions import ValidationError

from .models import User

logger = logging.getLogger(__name__)

INVALID_LINK = "This password reset link is invalid or has expired."
SECONDS_PER_MINUTE = 60
SUBJECT = "Réinitialisation du mot de passe / Password reset"
BODY = """Bonjour {name},

Vous avez demandé la réinitialisation de votre mot de passe. Ouvrez ce lien (valable {minutes} minutes) :
{link}

Si vous n'êtes pas à l'origine de cette demande, ignorez ce message : votre mot de passe reste inchangé.

---

Hello {name},

A password reset was requested for your account. Open this link (valid for {minutes} minutes):
{link}

If you did not request it, ignore this message: your password stays unchanged.
"""


def build_reset_link(user):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    return f"{settings.FRONTEND_URL}/reset-password?uid={uid}&token={token}"


def request_reset(email):
    """E-mail a reset link when the address belongs to an active account; otherwise do nothing.

    Failures are logged, never raised: the caller must answer identically in every case."""
    user = User.objects.filter(email=User.objects.normalize_email(email), is_active=True).first()
    if user is None:
        return
    message = BODY.format(
        name=user.first_name,
        minutes=settings.PASSWORD_RESET_TIMEOUT // SECONDS_PER_MINUTE,
        link=build_reset_link(user),
    )
    try:
        send_mail(SUBJECT, message, None, [user.email])
    except Exception:  # A broken mail server must not reveal which addresses exist.
        logger.exception("The password reset e-mail could not be sent")


def resolve_user(uid, token):
    """The active user a valid link belongs to; any defect gives the same generic error."""
    try:
        user = User.objects.filter(pk=force_str(urlsafe_base64_decode(uid)), is_active=True).first()
    except (TypeError, ValueError, OverflowError):
        user = None
    if user is None or not default_token_generator.check_token(user, token):
        raise ValidationError({"token": [INVALID_LINK]})
    return user