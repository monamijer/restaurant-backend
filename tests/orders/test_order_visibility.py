import pytest

from apps.orders.models import OrderStatus, OrderType

URL = "/api/orders/"

pytestmark = pytest.mark.django_db


def test_anonymous_cannot_list(api_client):
    assert api_client.get(URL).status_code == 401


def test_customers_only_see_their_own_orders(as_user, customer, create_user, make_order):
    mine = make_order(customer)
    make_order(create_user(email="other@example.com"))

    response = as_user(customer).get(URL)

    assert [order["id"] for order in response.data["results"]] == [mine.pk]


def test_staff_see_every_order_with_its_lines(
    as_user, staff_user, customer, make_order, dish, order_payload
):
    make_order(customer)
    as_user(customer).post(URL, order_payload(), format="json")

    response = as_user(staff_user).get(URL)

    assert response.data["count"] == 2
    assert any(order["items"] for order in response.data["results"])


def test_a_foreign_order_is_not_found(as_user, customer, create_user, make_order):
    foreign = make_order(create_user(email="other@example.com"))

    response = as_user(customer).get(f"{URL}{foreign.pk}/")

    assert response.status_code == 404


def test_filters_by_status_type_and_activity(as_user, staff_user, make_order, table):
    pending = make_order(status=OrderStatus.PENDING)
    ready = make_order(status=OrderStatus.READY, order_type=OrderType.DINE_IN, table=table)
    done = make_order(status=OrderStatus.COMPLETED)
    client = as_user(staff_user)

    by_status = client.get(URL, {"status": "ready"})
    by_type = client.get(URL, {"order_type": "dine_in"})
    in_progress = client.get(URL, {"active": "true"})
    finished = client.get(URL, {"active": "false"})

    assert [order["id"] for order in by_status.data["results"]] == [ready.pk]
    assert [order["id"] for order in by_type.data["results"]] == [ready.pk]
    assert {order["id"] for order in in_progress.data["results"]} == {pending.pk, ready.pk}
    assert [order["id"] for order in finished.data["results"]] == [done.pk]