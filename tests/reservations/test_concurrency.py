from datetime import time, timedelta

import pytest
from django.utils import timezone

from apps.core.models import RestaurantSettings
from apps.reservations import services
from apps.reservations.models import Reservation
from apps.tables.models import Table
from tests.concurrency_helpers import run_concurrently

ATTEMPTS = 8
LEAD_DAYS = 7


def booking_attempt(guest, table, window, restaurant):
    starts_at, ends_at = window
    return lambda: services.create_reservation(
        customer=guest,
        table_id=table.pk,
        starts_at=starts_at,
        ends_at=ends_at,
        party_size=2,
        restaurant=restaurant,
    )


@pytest.fixture
def window_and_settings(db):
    restaurant = RestaurantSettings.load()
    day = timezone.now().date() + timedelta(days=LEAD_DAYS)
    return services.build_window(restaurant, day, time(19, 0), 90), restaurant


@pytest.mark.django_db(transaction=True)
def test_simultaneous_bookings_of_one_table_admit_exactly_one(create_user, window_and_settings):
    window, restaurant = window_and_settings
    table = Table.objects.create(number=1, capacity=4)
    guests = [create_user(email=f"guest{n}@example.com") for n in range(ATTEMPTS)]

    outcomes = run_concurrently(
        [booking_attempt(guest, table, window, restaurant) for guest in guests]
    )

    assert sorted(outcomes) == sorted(["ok"] + ["conflict"] * (ATTEMPTS - 1))
    assert Reservation.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_simultaneous_bookings_of_different_tables_all_succeed(create_user, window_and_settings):
    window, restaurant = window_and_settings
    tables = [Table.objects.create(number=n, capacity=4) for n in range(1, 4)]
    guests = [create_user(email=f"guest{n}@example.com") for n in range(len(tables))]

    outcomes = run_concurrently(
        [booking_attempt(guest, table, window, restaurant) for guest, table in zip(guests, tables)]
    )

    assert outcomes == ["ok"] * len(tables)
    assert Reservation.objects.count() == len(tables)