import os

from django.conf import settings
from django.core.files.storage import FileSystemStorage


class PrivateStorage(FileSystemStorage):
    """Stores files under PRIVATE_MEDIA_ROOT, which no URL ever serves.

    The root is read at call time so tests can point it at a temporary folder. `url()` is
    unavailable on purpose: private files are only ever streamed by an authorised view."""

    @property
    def base_location(self):
        return settings.PRIVATE_MEDIA_ROOT

    @property
    def location(self):
        return os.path.abspath(self.base_location)

    @property
    def base_url(self):
        return None