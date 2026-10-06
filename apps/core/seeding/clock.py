"""Time travel for seeding only."""

from contextlib import contextmanager
from unittest import mock

from django.utils import timezone


@contextmanager
def frozen_at(moment):
    """Make every `timezone.now()` call return `moment`.

    Services read the clock through `timezone.now()` and models stamp `auto_now_add` fields
    with it, so anything created inside the block looks exactly as if it happened at
    `moment`. Used by the demo seed to build a believable history through the real services."""
    with mock.patch.object(timezone, "now", return_value=moment):
        yield