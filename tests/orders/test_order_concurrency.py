import pytest

from apps.core.models import RestaurantSettings
from apps.orders import services
from apps.orders.models import Order, OrderStatus, OrderType
from apps.tables.models import Table, TableStatus
from tests.concurrency_helpers import run_concurrently

ORDERS = 5


@pytest.fixture
def restaurant(db):
    return RestaurantSettings.load()


@pytest.mark.django_db(transaction=True)
def test_simultaneous_dine_in_orders_on_one_table_all_succeed(
    create_user, restaurant, dish, table
):
    guests = [create_user(email=f"guest{n}@example.com") for n in range(ORDERS)]
    lines = [{"menu_item_id": dish.pk, "quantity": 1}]

    outcomes = run_concurrently(
        [
            lambda guest=guest: services.create_order(
                customer=guest,
                order_type=OrderType.DINE_IN,
                lines=lines,
                table_id=table.pk,
                restaurant=restaurant,
            )
            for guest in guests
        ]
    )

    assert outcomes == ["ok"] * ORDERS
    assert Order.objects.count() == ORDERS
    assert Table.objects.get(pk=table.pk).status == TableStatus.OCCUPIED


@pytest.mark.django_db(transaction=True)
def test_simultaneous_completions_still_send_the_table_to_cleaning(make_order, table):
    table.status = TableStatus.OCCUPIED
    table.save()
    orders = [
        make_order(order_type=OrderType.DINE_IN, status=OrderStatus.READY, table=table, paid=True)
        for _ in range(ORDERS)
    ]

    outcomes = run_concurrently(
        [
            lambda order=order: services.update_status(order.pk, OrderStatus.COMPLETED)
            for order in orders
        ]
    )

    assert outcomes == ["ok"] * ORDERS
    assert Order.objects.filter(status=OrderStatus.COMPLETED).count() == ORDERS
    assert Table.objects.get(pk=table.pk).status == TableStatus.CLEANING