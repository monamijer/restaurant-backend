from contextlib import contextmanager
from datetime import time, timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.utils import timezone

from apps.core.models import RestaurantSettings
from apps.invoices.models import Invoice
from apps.menu.models import Category, MenuItem
from apps.notifications.models import Notification, NotificationType
from apps.orders.models import Order, OrderItem, OrderType
from apps.payments.models import Payment, PaymentMethod, PaymentStatus
from apps.queue_mgmt.models import QueueStatus, QueueTicket
from apps.reservations.models import Reservation
from apps.tables.models import Table

pytestmark = pytest.mark.django_db


@contextmanager
def rejected_by_database():
    """The block must be refused by the database without poisoning the test transaction."""
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            yield


@pytest.fixture
def category():
    return Category.objects.create(name="Mains")


@pytest.fixture
def menu_item(category):
    return MenuItem.objects.create(category=category, name="Grilled fish", price=Decimal("12.50"))


@pytest.fixture
def table():
    return Table.objects.create(number=1, capacity=4)


def make_order(**overrides):
    values = {
        "order_type": OrderType.TAKEAWAY,
        "subtotal": Decimal("10.00"),
        "tax_amount": Decimal("0.00"),
        "total": Decimal("10.00"),
    }
    values.update(overrides)
    return Order.objects.create(**values)


class TestRestaurantSettings:
    def test_load_creates_the_single_row_once(self):
        first = RestaurantSettings.load()
        second = RestaurantSettings.load()

        assert first.pk == second.pk == 1
        assert RestaurantSettings.objects.count() == 1

    def test_every_save_targets_the_singleton_row(self):
        RestaurantSettings(name="First").save()
        RestaurantSettings(name="Second").save()

        assert RestaurantSettings.objects.count() == 1
        assert RestaurantSettings.load().name == "Second"

    def test_cannot_be_deleted(self):
        with pytest.raises(ProtectedError):
            RestaurantSettings.load().delete()

    def test_rejects_unknown_timezone(self):
        settings = RestaurantSettings.load()
        settings.timezone = "Mars/Olympus"

        with pytest.raises(ValidationError):
            settings.full_clean()

    def test_rejects_closing_time_before_opening_time(self):
        settings = RestaurantSettings.load()
        settings.opening_time = time(20, 0)
        settings.closing_time = time(8, 0)

        with rejected_by_database():
            settings.save()


class TestMenu:
    def test_slugs_are_generated_and_unique(self, category):
        first = MenuItem.objects.create(category=category, name="Grilled fish", price=Decimal("9.00"))
        second = MenuItem.objects.create(category=category, name="Grilled fish", price=Decimal("9.00"))

        assert first.slug == "grilled-fish"
        assert second.slug == "grilled-fish-2"

    def test_negative_price_is_rejected(self, category):
        with rejected_by_database():
            MenuItem.objects.create(category=category, name="Broken", price=Decimal("-1.00"))


class TestTables:
    def test_table_numbers_are_unique(self, table):
        with rejected_by_database():
            Table.objects.create(number=table.number, capacity=2)

    def test_capacity_must_be_positive(self):
        with rejected_by_database():
            Table.objects.create(number=9, capacity=0)


class TestReservations:
    def test_cannot_end_before_it_starts(self, create_user, table):
        customer = create_user()
        starts_at = timezone.now() + timedelta(days=1)

        with rejected_by_database():
            Reservation.objects.create(
                customer=customer,
                table=table,
                starts_at=starts_at,
                ends_at=starts_at - timedelta(hours=1),
                party_size=2,
            )


class TestQueue:
    def test_walk_in_guest_needs_no_account(self):
        ticket = QueueTicket.objects.create(customer_name="Walk-in", party_size=3)

        assert ticket.customer is None
        assert ticket.status == QueueStatus.WAITING


class TestOrders:
    def test_total_must_equal_subtotal_plus_tax(self):
        with rejected_by_database():
            make_order(total=Decimal("99.00"))

    def test_line_subtotal_must_equal_quantity_times_price(self, menu_item):
        order = make_order()

        with rejected_by_database():
            OrderItem.objects.create(
                order=order,
                menu_item=menu_item,
                item_name=menu_item.name,
                quantity=2,
                unit_price=Decimal("12.50"),
                subtotal=Decimal("9.00"),
            )

    def test_order_item_keeps_the_historical_price(self, menu_item):
        item = OrderItem.objects.create(
            order=make_order(),
            menu_item=menu_item,
            item_name=menu_item.name,
            quantity=2,
            unit_price=Decimal("12.50"),
            subtotal=Decimal("25.00"),
        )

        menu_item.price = Decimal("99.00")
        menu_item.save()
        item.refresh_from_db()

        assert item.unit_price == Decimal("12.50")

    def test_menu_item_used_in_an_order_cannot_be_deleted(self, menu_item):
        OrderItem.objects.create(
            order=make_order(),
            menu_item=menu_item,
            item_name=menu_item.name,
            quantity=1,
            unit_price=Decimal("12.50"),
            subtotal=Decimal("12.50"),
        )

        with pytest.raises(ProtectedError):
            menu_item.delete()


class TestPayments:
    def test_references_are_generated_and_unique(self):
        order = make_order()
        first = Payment.objects.create(order=order, method=PaymentMethod.CASH, amount=Decimal("5.00"))
        second = Payment.objects.create(order=order, method=PaymentMethod.CARD, amount=Decimal("5.00"))

        assert first.reference.startswith("PAY-")
        assert first.reference != second.reference

    def test_paid_payment_requires_a_paid_timestamp(self):
        with rejected_by_database():
            Payment.objects.create(
                order=make_order(),
                method=PaymentMethod.CASH,
                amount=Decimal("10.00"),
                status=PaymentStatus.PAID,
            )


class TestInvoices:
    def test_an_order_has_at_most_one_invoice(self):
        order = make_order()
        Invoice.objects.create(order=order, invoice_number="INV-2026-000001", total=Decimal("10.00"))

        with rejected_by_database():
            Invoice.objects.create(order=order, invoice_number="INV-2026-000002", total=Decimal("10.00"))


class TestNotifications:
    def test_notifications_start_unread(self, create_user):
        notification = Notification.objects.create(
            user=create_user(), type=NotificationType.ORDER, message="Your order is ready."
        )

        assert notification.is_read is False