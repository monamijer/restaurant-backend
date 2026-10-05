import pytest

from apps.orders.models import OrderStatus
from apps.payments.models import Payment, PaymentMethod, PaymentStatus

ORDERS_URL = "/api/orders/"

pytestmark = pytest.mark.django_db


def set_status(client, order, new_status):
    return client.post(
        f"{ORDERS_URL}{order.pk}/update-status/", {"status": new_status}, format="json"
    )


def test_an_unpaid_order_cannot_be_completed(as_user, staff_user, make_order):
    order = make_order(status=OrderStatus.READY)

    response = set_status(as_user(staff_user), order, "completed")

    assert response.status_code == 409
    assert "not fully paid" in response.data["message"]


def test_a_paid_order_can_be_completed(as_user, staff_user, make_order):
    order = make_order(status=OrderStatus.READY, paid=True)

    response = set_status(as_user(staff_user), order, "completed")

    assert response.status_code == 200
    assert response.data["status"] == "completed"


def test_a_paid_order_cannot_be_cancelled(as_user, staff_user, make_order):
    order = make_order(status=OrderStatus.CONFIRMED, paid=True)

    response = set_status(as_user(staff_user), order, "cancelled")

    assert response.status_code == 409
    assert "refund" in response.data["message"]


def test_cancelling_an_order_fails_its_pending_payments(as_user, staff_user, make_order):
    order = make_order()
    pending = Payment.objects.create(
        order=order, method=PaymentMethod.CASH, amount=order.total
    )

    response = set_status(as_user(staff_user), order, "cancelled")

    pending.refresh_from_db()
    assert response.status_code == 200
    assert pending.status == PaymentStatus.FAILED