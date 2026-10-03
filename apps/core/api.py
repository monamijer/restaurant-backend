"""Small building blocks shared by every API app."""

from django.db.models import ProtectedError
from rest_framework import status
from rest_framework.exceptions import APIException


class ConflictError(APIException):
    """HTTP 409: the request is valid but clashes with the current state of the data."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = "The request conflicts with the current state of the resource."
    default_code = "conflict"


class ProtectedDeleteMixin:
    """Turn a PROTECT integrity refusal into a clean 409 instead of a server error."""

    delete_conflict_message = (
        "This record is referenced by other records and cannot be deleted. Deactivate it instead."
    )

    def perform_destroy(self, instance):
        try:
            instance.delete()
        except ProtectedError:
            raise ConflictError(self.delete_conflict_message)