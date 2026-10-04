"""Reservation business rules: the single authority for booking a table.

Concurrency model
-----------------
Every write that depends on a table's calendar first takes a row lock on that table
(SELECT ... FOR UPDATE). Concurrent attempts on the same table therefore run one after
the other, and each overlap check sees the bookings committed before it. The overlap
query is itself a locking read, so it reads the latest committed data instead of the
transaction snapshot. Locks are always taken in the same order: table, then reservations.

Expiry model
------------
A pending request holds its slot until `expires_at`. A lapsed hold never blocks anyone
(see `blocking`), and `expire_stale_pending` turns lapsed holds into `expired` rows.
"""

from datetime import UTC, datetime, timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.accounts.permissions import STAFF_ROLES
from apps.core.api import ConflictError
from apps.core.models import RestaurantSettings
from apps.notifications import services as notifications
from apps.notifications.models import NotificationType
from apps.tables.models import Table

from .models import Reservation, ReservationStatus

MINUTES_PER_HOUR = 60

ALLOWED_TRANSITIONS = {
    ReservationStatus.PENDING: {
        ReservationStatus.CONFIRMED,
        ReservationStatus.REJECTED,
        ReservationStatus.CANCELLED,
    },
    ReservationStatus.CONFIRMED: {
        ReservationStatus.CANCELLED,
        ReservationStatus.COMPLETED,
        ReservationStatus.NO_SHOW,
    },
}


# --- Time helpers -------------------------------------------------------------------
def _minutes_of_day(wall_time):
    return wall_time.hour * MINUTES_PER_HOUR + wall_time.minute


def _minutes_between(starts_at, ends_at):
    return int((ends_at - starts_at).total_seconds() // MINUTES_PER_HOUR)


def _describe(instant, restaurant):
    return f"{instant.astimezone(restaurant.zone):%Y-%m-%d at %H:%M}"


def local_wall_to_utc(day, wall_time, zone):
    """Read a wall-clock time in the restaurant timezone as a UTC instant.

    Returns None when that local time does not exist (the hour skipped by a DST change)."""
    naive = datetime.combine(day, wall_time)
    instant = naive.replace(tzinfo=zone).astimezone(UTC)
    if instant.astimezone(zone).replace(tzinfo=None) != naive:
        return None
    return instant


def build_window(restaurant, day, wall_time, duration_minutes):
    starts_at = local_wall_to_utc(day, wall_time, restaurant.zone)
    if starts_at is None:
        raise ValidationError({"time": ["This local time does not exist (daylight saving change)."]})
    return starts_at, starts_at + timedelta(minutes=duration_minutes)


# --- Validation ---------------------------------------------------------------------
def _duration_errors(restaurant, duration):
    step = restaurant.slot_step_minutes
    low, high = restaurant.min_reservation_minutes, restaurant.max_reservation_minutes
    if duration % step or not low <= duration <= high:
        return {
            "duration_minutes": [
                f"Duration must be a multiple of {step} minutes between {low} and {high}."
            ]
        }
    return {}


def _window_errors(restaurant, starts_at, ends_at, now):
    zone = restaurant.zone
    local_start, local_end = starts_at.astimezone(zone), ends_at.astimezone(zone)
    errors = {}
    if starts_at <= now:
        errors["date"] = ["The reservation must start in the future."]
    errors.update(_duration_errors(restaurant, _minutes_between(starts_at, ends_at)))
    ends_too_late = (
        local_end.date() != local_start.date() or local_end.time() > restaurant.closing_time
    )
    if "duration_minutes" not in errors and ends_too_late:
        errors["duration_minutes"] = [
            f"The reservation must end by {restaurant.closing_time:%H:%M}."
        ]
    offset = _minutes_of_day(local_start.time()) - _minutes_of_day(restaurant.opening_time)
    off_grid = (
        offset % restaurant.slot_step_minutes != 0
        or local_start.second != 0
        or local_start.microsecond != 0
    )
    if local_start.time() < restaurant.opening_time or off_grid:
        errors["time"] = [
            f"Reservations start from {restaurant.opening_time:%H:%M}, "
            f"every {restaurant.slot_step_minutes} minutes."
        ]
    return errors


def _party_errors(table, party_size):
    if party_size > table.capacity:
        return {"party_size": [f"Table {table.number} seats at most {table.capacity} guests."]}
    return {}


def blocking(now):
    """Reservations that currently hold a table: confirmed, or pending and not yet lapsed."""
    return Q(status=ReservationStatus.CONFIRMED) | Q(
        status=ReservationStatus.PENDING, expires_at__gt=now
    )


# --- Booking ------------------------------------------------------------------------
def create_reservation(
    *, customer, table_id, starts_at, ends_at, party_size, notes="", restaurant=None, now=None
):
    restaurant = restaurant or RestaurantSettings.load()
    now = now or timezone.now()
    with transaction.atomic():
        # Lock first: serialise every booking attempt on this table before reading anything.
        table = Table.objects.select_for_update().filter(pk=table_id).first()
        if table is None:
            raise ValidationError({"table": ["Unknown table."]})

        errors = {
            **_window_errors(restaurant, starts_at, ends_at, now),
            **_party_errors(table, party_size),
        }
        if errors:
            raise ValidationError(errors)

        clash = (
            Reservation.objects.select_for_update()
            .filter(blocking(now), table=table, starts_at__lt=ends_at, ends_at__gt=starts_at)
            .values_list("pk", flat=True)[:1]
        )
        if list(clash):
            raise ConflictError("This table is already booked for part of the requested time.")

        reservation = Reservation.objects.create(
            customer=customer,
            table=table,
            starts_at=starts_at,
            ends_at=ends_at,
            party_size=party_size,
            notes=notes,
            status=ReservationStatus.PENDING,
            expires_at=now + timedelta(minutes=restaurant.pending_reservation_expiry_minutes),
        )
        notifications.notify_staff(
            NotificationType.RESERVATION,
            f"New reservation request from {customer.full_name} for {party_size} guest(s) "
            f"on {_describe(starts_at, restaurant)} (table {table.number}).",
        )
    return reservation


# --- Status changes -----------------------------------------------------------------
def _lock(reservation_id):
    return Reservation.objects.select_for_update().get(pk=reservation_id)


def _apply(reservation, new_status):
    if new_status not in ALLOWED_TRANSITIONS.get(reservation.status, set()):
        raise ConflictError(
            f"A reservation that is '{reservation.status!s}' cannot become '{new_status!s}'."
        )
    reservation.status = new_status
    if new_status == ReservationStatus.CONFIRMED:
        reservation.expires_at = None  # The hold becomes a firm booking.
    reservation.save(update_fields=["status", "expires_at", "updated_at"])


def confirm_reservation(reservation_id, *, now=None):
    now = now or timezone.now()
    restaurant = RestaurantSettings.load()
    with transaction.atomic():
        reservation = _lock(reservation_id)
        lapsed = reservation.expires_at is not None and reservation.expires_at <= now
        if reservation.status == ReservationStatus.PENDING and lapsed:
            raise ConflictError("This reservation request has expired.")
        _apply(reservation, ReservationStatus.CONFIRMED)
        notifications.notify(
            reservation.customer,
            NotificationType.RESERVATION,
            f"Your reservation for {_describe(reservation.starts_at, restaurant)} is confirmed.",
        )
    return reservation


def reject_reservation(reservation_id):
    restaurant = RestaurantSettings.load()
    with transaction.atomic():
        reservation = _lock(reservation_id)
        _apply(reservation, ReservationStatus.REJECTED)
        notifications.notify(
            reservation.customer,
            NotificationType.RESERVATION,
            f"Your reservation request for {_describe(reservation.starts_at, restaurant)} "
            "could not be accepted.",
        )
    return reservation


def cancel_reservation(reservation_id, *, actor, now=None):
    now = now or timezone.now()
    restaurant = RestaurantSettings.load()
    with transaction.atomic():
        reservation = _lock(reservation_id)
        is_staff = actor.role in STAFF_ROLES
        if not is_staff:
            # Defence in depth: the view already scopes the queryset to the owner.
            if reservation.customer_id != actor.pk:
                raise PermissionDenied()
            if reservation.starts_at <= now:
                raise ConflictError(
                    "A reservation that has already started can only be cancelled by staff."
                )
        _apply(reservation, ReservationStatus.CANCELLED)

        when = _describe(reservation.starts_at, restaurant)
        if reservation.customer_id == actor.pk:
            notifications.notify_staff(
                NotificationType.RESERVATION,
                f"{reservation.customer.full_name} cancelled the reservation for {when}.",
            )
        else:
            notifications.notify(
                reservation.customer,
                NotificationType.RESERVATION,
                f"Your reservation for {when} was cancelled by the restaurant.",
            )
    return reservation


def complete_reservation(reservation_id):
    with transaction.atomic():
        reservation = _lock(reservation_id)
        _apply(reservation, ReservationStatus.COMPLETED)
    return reservation


def mark_no_show(reservation_id):
    with transaction.atomic():
        reservation = _lock(reservation_id)
        _apply(reservation, ReservationStatus.NO_SHOW)
    return reservation


def expire_stale_pending(*, now=None):
    """Turn lapsed pending requests into 'expired' and tell their customers.

    Tables are processed one at a time, each under that table's lock, so the lock order
    (table, then reservations) is the same as for booking and cannot deadlock with it."""
    now = now or timezone.now()
    table_ids = sorted(
        set(
            Reservation.objects.filter(
                status=ReservationStatus.PENDING, expires_at__lte=now
            ).values_list("table_id", flat=True)
        )
    )
    if not table_ids:
        return 0

    restaurant = RestaurantSettings.load()
    expired = 0
    for table_id in table_ids:
        with transaction.atomic():
            Table.objects.select_for_update().filter(pk=table_id).first()
            stale = list(
                Reservation.objects.select_for_update().filter(
                    table_id=table_id, status=ReservationStatus.PENDING, expires_at__lte=now
                )
            )
            for reservation in stale:
                reservation.status = ReservationStatus.EXPIRED
                reservation.save(update_fields=["status", "updated_at"])
                notifications.notify(
                    reservation.customer,
                    NotificationType.RESERVATION,
                    f"Your reservation request for "
                    f"{_describe(reservation.starts_at, restaurant)} expired before it was confirmed.",
                )
            expired += len(stale)
    return expired


# --- Availability -------------------------------------------------------------------
def get_availability(*, restaurant, day, party_size, duration_minutes, now=None):
    """Every start slot of `day` with the tables that can take `party_size` for that long."""
    now = now or timezone.now()
    errors = _duration_errors(restaurant, duration_minutes)
    if errors:
        raise ValidationError(errors)

    step = timedelta(minutes=restaurant.slot_step_minutes)
    duration = timedelta(minutes=duration_minutes)
    closing = datetime.combine(day, restaurant.closing_time)

    candidates = []
    local_start = datetime.combine(day, restaurant.opening_time)
    while local_start + duration <= closing:
        starts_at = local_wall_to_utc(day, local_start.time(), restaurant.zone)
        if starts_at is not None and starts_at > now:
            candidates.append((local_start.time(), starts_at, starts_at + duration))
        local_start += step
    if not candidates:
        return []

    tables = list(Table.objects.filter(capacity__gte=party_size).order_by("number"))
    window_start, window_end = candidates[0][1], candidates[-1][2]
    booked = list(
        Reservation.objects.filter(
            blocking(now), table__in=tables, starts_at__lt=window_end, ends_at__gt=window_start
        ).values_list("table_id", "starts_at", "ends_at")
    )

    slots = []
    for wall_time, starts_at, ends_at in candidates:
        free = [
            table
            for table in tables
            if not any(
                table_id == table.pk and start < ends_at and end > starts_at
                for table_id, start, end in booked
            )
        ]
        if free:
            slots.append({"starts_at": starts_at, "time": wall_time, "tables": free})
    return slots