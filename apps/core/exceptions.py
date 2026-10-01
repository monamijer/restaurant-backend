"""Single error envelope for the whole API: {success, message, errors, code}."""

from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.views import exception_handler

VALIDATION_MESSAGE = "Validation failed."
FALLBACK_MESSAGE = "Request failed."
DEFAULT_ERROR_CODE = "ERROR"

ERROR_CODES_BY_STATUS = {
    status.HTTP_400_BAD_REQUEST: "BAD_REQUEST",
    status.HTTP_401_UNAUTHORIZED: "AUTHENTICATION_FAILED",
    status.HTTP_403_FORBIDDEN: "PERMISSION_DENIED",
    status.HTTP_404_NOT_FOUND: "NOT_FOUND",
    status.HTTP_405_METHOD_NOT_ALLOWED: "METHOD_NOT_ALLOWED",
    status.HTTP_409_CONFLICT: "CONFLICT",
    status.HTTP_429_TOO_MANY_REQUESTS: "THROTTLED",
}


def _field_errors(data):
    """Validation data is a dict of field errors, or a bare list for non-field errors."""
    return data if isinstance(data, dict) else {"non_field_errors": data}


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return None  # Unhandled exception: let Django produce the 500.

    if isinstance(exc, ValidationError):
        message = VALIDATION_MESSAGE
        errors = _field_errors(response.data)
        code = "VALIDATION_ERROR"
    else:
        detail = response.data.get("detail") if isinstance(response.data, dict) else None
        message = str(detail) if detail else FALLBACK_MESSAGE
        errors = {}
        code = ERROR_CODES_BY_STATUS.get(response.status_code, DEFAULT_ERROR_CODE)

    response.data = {"success": False, "message": message, "errors": errors, "code": code}
    return response
