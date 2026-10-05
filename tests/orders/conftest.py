from decimal import Decimal

import pytest

from apps.menu.models import Category, MenuItem
from apps.orders.models import Order, OrderStatus, OrderType
from apps.tables.models import Table


@pytest.fixture
def category(db):
    return Category.objects.create(name="Mains")


@pytest.fixture
def dish(category):
    return MenuItem.objects.create(category=category, name="Grilled fish", price=Decimal("12.50"))


@pytest.fixture
def side(category):
    return MenuItem.objects.create(category=category, name="Fries", price=Decimal("6.00"))


@pytest.fixture
def table(db):
    return Table.objects.create(number=1, capacity=4)


@pytest.fixture
def order_payload(dish):
    def build(**overrides):
        payload = {
            "order_type": "takeaway",
            "items": [{"menu_item": dish.pk, "quantity": 2}],
        }
        payload.update(overrides)
        return payload

    return build


@pytest.fixture
def make_order():
    """Insert an order directly (for arranging state), bypassing the pricing service."""

    def factory(
        customer=None,
        *,
        order_type=OrderType.TAKEAWAY,
        status=OrderStatus.PENDING,
        table=None,
        total=Decimal("10.00"),
    ):
        return Order.objects.create(
            customer=customer,
            table=table,
            order_type=order_type,
            status=status,
            subtotal=total,
            tax_amount=Decimal("0.00"),
            total=total,
        )

    return factory