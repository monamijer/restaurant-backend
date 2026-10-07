from datetime import UTC, date, datetime, time
from decimal import Decimal

import pytest

from apps.menu.models import Category, MenuItem
from apps.orders.models import Order, OrderItem, OrderStatus, OrderType
from apps.payments.models import Payment, PaymentMethod, PaymentStatus
from apps.tables.models import Table


@pytest.fixture
def dish(db):
    category = Category.objects.create(name="Mains")
    return MenuItem.objects.create(category=category, name="Grilled fish", price=Decimal("12.50"))


@pytest.fixture
def side(dish):
    return MenuItem.objects.create(category=dish.category, name="Fries", price=Decimal("6.00"))


@pytest.fixture
def table(db):
    return Table.objects.create(number=1, capacity=4)


def at(year, month, day, hour=12, minute=0):
    """A UTC instant, to place sales at exact moments."""
    return datetime.combine(date(year, month, day), time(hour, minute), tzinfo=UTC)


@pytest.fixture
def record_sale(dish):
    """Insert an order with its lines and payment at a chosen moment (no taxes, no PDFs)."""

    def factory(
        when,
        *,
        lines=None,
        customer=None,
        order_type=OrderType.TAKEAWAY,
        table=None,
        status=OrderStatus.COMPLETED,
        paid=True,
    ):
        lines = lines or [(dish, 1)]
        total = sum((item.price * quantity for item, quantity in lines), Decimal("0.00"))
        order = Order.objects.create(
            customer=customer,
            table=table,
            order_type=order_type,
            status=status,
            subtotal=total,
            tax_amount=Decimal("0.00"),
            total=total,
        )
        Order.objects.filter(pk=order.pk).update(created_at=when)
        for item, quantity in lines:
            OrderItem.objects.create(
                order=order,
                menu_item=item,
                item_name=item.name,
                quantity=quantity,
                unit_price=item.price,
                subtotal=item.price * quantity,
            )
        if paid:
            payment = Payment.objects.create(
                order=order,
                method=PaymentMethod.CASH,
                amount=total,
                status=PaymentStatus.PAID,
                paid_at=when,
            )
            Payment.objects.filter(pk=payment.pk).update(created_at=when)
        return order

    return factory