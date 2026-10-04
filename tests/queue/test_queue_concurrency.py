import pytest

from apps.core.models import RestaurantSettings
from apps.queue_mgmt import services
from apps.queue_mgmt.models import QueueStatus, QueueTicket
from tests.concurrency_helpers import run_concurrently

ATTEMPTS = 6
WAITING_TICKETS = 3
CALLERS = 5


@pytest.fixture
def restaurant(db):
    return RestaurantSettings.load()


def join(guest):
    return lambda: services.join_queue(customer=guest, name="Guest", phone="", party_size=2)


@pytest.mark.django_db(transaction=True)
def test_one_account_cannot_hold_two_tickets_even_when_racing(create_user, restaurant):
    guest = create_user(email="guest@example.com")

    outcomes = run_concurrently([join(guest) for _ in range(ATTEMPTS)])

    assert sorted(outcomes) == sorted(["ok"] + ["conflict"] * (ATTEMPTS - 1))
    assert QueueTicket.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_simultaneous_joins_get_distinct_consecutive_places(create_user, restaurant):
    guests = [create_user(email=f"guest{n}@example.com") for n in range(ATTEMPTS)]

    outcomes = run_concurrently([join(guest) for guest in guests])

    assert outcomes == ["ok"] * ATTEMPTS
    step = restaurant.queue_minutes_per_party
    quoted = sorted(QueueTicket.objects.values_list("estimated_wait_time", flat=True))
    assert quoted == [rank * step for rank in range(ATTEMPTS)]
    assert sorted(services.waiting_positions().values()) == list(range(1, ATTEMPTS + 1))


@pytest.mark.django_db(transaction=True)
def test_racing_staff_never_call_the_same_ticket_twice(restaurant):
    for number in range(WAITING_TICKETS):
        QueueTicket.objects.create(customer_name=f"Guest {number}", party_size=2)

    outcomes = run_concurrently([services.call_next for _ in range(CALLERS)])

    assert sorted(outcomes) == ["conflict"] * (CALLERS - WAITING_TICKETS) + ["ok"] * WAITING_TICKETS
    assert QueueTicket.objects.filter(status=QueueStatus.CALLED).count() == WAITING_TICKETS