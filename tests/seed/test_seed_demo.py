from collections import defaultdict
from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from apps.accounts.models import Role, User
from apps.invoices.models import Invoice
from apps.menu.models import MenuItem
from apps.orders.models import Order, OrderStatus
from apps.payments import services as payment_services
from apps.queue_mgmt.models import QueueStatus, QueueTicket
from apps.reservations.models import Reservation, ReservationStatus
from apps.tables.models import Table

pytestmark = pytest.mark.django_db

SMALL_SEED = ["--force", "--days", "2", "--orders-per-day", "3", "--no-images"]
OCCUPYING = (
    ReservationStatus.PENDING,
    ReservationStatus.CONFIRMED,
    ReservationStatus.COMPLETED,
    ReservationStatus.NO_SHOW,
)


def run_seed(*extra):
    output = StringIO()
    call_command("seed_demo", *extra, stdout=output)
    return output.getvalue()


@pytest.fixture
def seeded():
    run_seed(*SMALL_SEED)


def test_the_seed_refuses_to_run_without_debug_unless_forced():
    with pytest.raises(CommandError):
        run_seed("--days", "1", "--no-images")


def test_every_role_gets_demo_accounts(seeded):
    roles = set(
        User.objects.filter(email__endswith="@demo.example").values_list("role", flat=True)
    )

    assert roles == {Role.ADMIN, Role.STAFF, Role.CLIENT}


def test_orders_are_arithmetically_consistent(seeded):
    assert Order.objects.exists()
    for order in Order.objects.prefetch_related("items"):
        assert order.subtotal == sum(item.subtotal for item in order.items.all())
        assert order.total == order.subtotal + order.tax_amount


def test_completed_orders_are_fully_paid_and_invoiced(seeded):
    completed = Order.objects.filter(status=OrderStatus.COMPLETED)

    assert completed.exists()
    for order in completed:
        assert payment_services.paid_total(order.pk) >= order.total
        assert Invoice.objects.filter(order=order).exists()


def test_invoice_numbers_are_gapless_within_each_year(seeded):
    by_year = defaultdict(list)
    for number in Invoice.objects.values_list("invoice_number", flat=True):
        _, year, sequence = number.split("-")
        by_year[year].append(int(sequence))

    assert by_year
    for sequences in by_year.values():
        assert sorted(sequences) == list(range(1, len(sequences) + 1))


def test_no_two_occupying_reservations_overlap_on_a_table(seeded):
    by_table = defaultdict(list)
    for reservation in Reservation.objects.filter(status__in=OCCUPYING):
        by_table[reservation.table_id].append(reservation)

    assert by_table
    for reservations in by_table.values():
        reservations.sort(key=lambda r: r.starts_at)
        for earlier, later in zip(reservations, reservations[1:]):
            assert earlier.ends_at <= later.starts_at


def test_the_queue_shows_every_ticket_state(seeded):
    states = set(QueueTicket.objects.values_list("status", flat=True))

    assert states == {
        QueueStatus.WAITING,
        QueueStatus.CALLED,
        QueueStatus.SEATED,
        QueueStatus.CANCELLED,
    }


def test_the_seed_does_not_create_duplicates_when_run_twice(seeded):
    orders_before = Order.objects.count()

    message = run_seed(*SMALL_SEED)

    assert "already present" in message
    assert Order.objects.count() == orders_before
    assert User.objects.filter(email__endswith="@demo.example").count() == 9


def test_reset_rebuilds_the_data_and_spares_other_accounts(seeded, create_user):
    create_user(email="real.person@example.com")

    run_seed(*SMALL_SEED, "--reset")

    assert User.objects.filter(email="real.person@example.com").exists()
    assert User.objects.filter(email__endswith="@demo.example").count() == 9
    assert Table.objects.count() == 10


def test_placeholder_images_are_written_when_requested(settings):
    run_seed("--force", "--days", "1", "--orders-per-day", "1")

    pictured = MenuItem.objects.exclude(image="")
    assert pictured.count() == MenuItem.objects.count()
    assert all((settings.MEDIA_ROOT / item.image.name).exists() for item in pictured)