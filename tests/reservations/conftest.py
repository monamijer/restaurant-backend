from datetime import UTC, datetime, time, timedelta

import pytest
from django.utils import timezone

from apps.reservations.models import Reservation, ReservationStatus
from apps.tables.models import Table

BOOKING_LEAD_DAYS = 7


@pytest.fixture
def booking_day():
    return timezone.now().date() + timedelta(days=BOOKING_LEAD_DAYS)


@pytest.fixture
def table(db):
    return Table.objects.create(number=1, capacity=4)


@pytest.fixture
def booking_payload(table, booking_day):
    def build(**overrides):
        payload = {
            "table": table.pk,
            "date": booking_day.isoformat(),
            "time": "19:00",
            "duration_minutes": 90,
            "party_size": 2,
        }
        payload.update(overrides)
        return payload

    return build


@pytest.fixture
def make_reservation(table, booking_day):
    """Insert a reservation directly, bypassing the service (for arranging test state)."""

    def factory(
        customer,
        *,
        on_table=None,
        day=None,
        hour=19,
        minutes=90,
        status=ReservationStatus.CONFIRMED,
        **extra,
    ):
        starts_at = datetime.combine(day or booking_day, time(hour, 0), tzinfo=UTC)
        extra.setdefault("party_size", 2)
        return Reservation.objects.create(
            customer=customer,
            table=on_table or table,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(minutes=minutes),
            status=status,
            **extra,
        )

    return factory