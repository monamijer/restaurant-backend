"""Virtual queue business rules.

Concurrency model
-----------------
Queue operations are rare and short, so every mutation takes one mutex: a row lock on the
singleton settings row (see `queue_lock`). That keeps "one active ticket per account",
"call the next ticket" and the quoted wait time correct without per-case reasoning. The lock
is always the first statement of its transaction, so the reads that follow see the latest
committed data.

Position model
--------------
A position is never stored. `waiting_positions` is the only place that computes it.
"""

from contextlib import contextmanager

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from apps.accounts.permissions import STAFF_ROLES
from apps.core.api import ConflictError
from apps.core.models import SINGLETON_PK, RestaurantSettings
from apps.notifications import services as notifications
from apps.notifications.models import NotificationType

from .models import QueueStatus, QueueTicket

ACTIVE_STATUSES = (QueueStatus.WAITING, QueueStatus.CALLED)
FINISHED_STATUSES = (QueueStatus.SEATED, QueueStatus.NO_SHOW, QueueStatus.CANCELLED)

ALLOWED_TRANSITIONS = {
    QueueStatus.WAITING: {QueueStatus.CALLED, QueueStatus.CANCELLED},
    QueueStatus.CALLED: {QueueStatus.SEATED, QueueStatus.NO_SHOW, QueueStatus.CANCELLED},
}


# --- Reading ------------------------------------------------------------------------
def waiting_positions():
    """{ticket_id: position} for every waiting ticket, in order of arrival (1 is next)."""
    waiting_ids = QueueTicket.objects.filter(status=QueueStatus.WAITING).order_by("pk")
    return {pk: rank for rank, pk in enumerate(waiting_ids.values_list("pk", flat=True), start=1)}


def estimate_wait_minutes(position, restaurant):
    """Minutes until a table for the party at `position`; None when it is not waiting."""
    if position is None:
        return None
    return (position - 1) * restaurant.queue_minutes_per_party


# --- Internals ----------------------------------------------------------------------
@contextmanager
def queue_lock():
    """Serialise every queue mutation. Yields the locked settings row."""
    RestaurantSettings.load()  # Outside the transaction: guarantees the row exists.
    with transaction.atomic():
        yield RestaurantSettings.objects.select_for_update().get(pk=SINGLETON_PK)


def _apply(ticket, new_status, now):
    if new_status not in ALLOWED_TRANSITIONS.get(ticket.status, set()):
        raise ConflictError(
            f"A ticket that is '{ticket.status!s}' cannot become '{new_status!s}'."
        )
    ticket.status = new_status
    fields = ["status"]
    if new_status == QueueStatus.CALLED:
        ticket.called_at = now
        fields.append("called_at")
    if new_status in FINISHED_STATUSES:
        ticket.completed_at = now
        fields.append("completed_at")
    ticket.save(update_fields=fields)


def _call(ticket, now):
    _apply(ticket, QueueStatus.CALLED, now)
    if ticket.customer_id is not None:
        notifications.notify(
            ticket.customer,
            NotificationType.QUEUE,
            "Your table is almost ready: please come to the host stand now.",
        )


# --- Operations ---------------------------------------------------------------------
def join_queue(*, customer, name, phone, party_size):
    """Add a party to the end of the queue. `customer` is None for a walk-in guest."""
    with queue_lock() as restaurant:
        if (
            customer is not None
            and QueueTicket.objects.filter(customer=customer, status__in=ACTIVE_STATUSES).exists()
        ):
            raise ConflictError("You already have an active ticket in the queue.")
        position = len(waiting_positions()) + 1
        return QueueTicket.objects.create(
            customer=customer,
            customer_name=name,
            phone=phone,
            party_size=party_size,
            status=QueueStatus.WAITING,
            estimated_wait_time=estimate_wait_minutes(position, restaurant),
        )


def call_next(*, now=None):
    now = now or timezone.now()
    with queue_lock():
        ticket = QueueTicket.objects.filter(status=QueueStatus.WAITING).order_by("pk").first()
        if ticket is None:
            raise ConflictError("The queue is empty.")
        _call(ticket, now)
    return ticket


def call_ticket(ticket_id, *, now=None):
    now = now or timezone.now()
    with queue_lock():
        ticket = QueueTicket.objects.get(pk=ticket_id)
        _call(ticket, now)
    return ticket


def seat_ticket(ticket_id, *, now=None):
    now = now or timezone.now()
    with queue_lock():
        ticket = QueueTicket.objects.get(pk=ticket_id)
        _apply(ticket, QueueStatus.SEATED, now)
    return ticket


def mark_no_show(ticket_id, *, now=None):
    now = now or timezone.now()
    with queue_lock():
        ticket = QueueTicket.objects.get(pk=ticket_id)
        _apply(ticket, QueueStatus.NO_SHOW, now)
    return ticket


def cancel_ticket(ticket_id, *, actor, now=None):
    now = now or timezone.now()
    with queue_lock():
        ticket = QueueTicket.objects.get(pk=ticket_id)
        is_staff = actor.role in STAFF_ROLES
        if not is_staff and ticket.customer_id != actor.pk:
            # Defence in depth: the view already scopes the queryset to the owner.
            raise PermissionDenied()
        _apply(ticket, QueueStatus.CANCELLED, now)
        if ticket.customer_id is not None and ticket.customer_id != actor.pk:
            notifications.notify(
                ticket.customer,
                NotificationType.QUEUE,
                "You were removed from the waiting queue by the restaurant.",
            )
    return ticket