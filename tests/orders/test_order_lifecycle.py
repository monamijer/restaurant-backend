import pytest

from apps.notifications.models import Notification
from apps.orders.models import OrderStatus, OrderType
from apps.tables.models import TableStatus

URL = "/api/orders/"

pytestmark = pytest.mark.django_db


def set_status(client, order, new_status):
    return client.post(f"{URL}{order.pk}/update-status/", {"status": new_status}, format="json")


class TestStatusMachine:
    def test_staff_walk_an_order_through_its_lifecycle(
        self, as_user, staff_user, customer, make_order
    ):
        order = make_order(customer)
        client = as_user(staff_user)

        for new_status in ["confirmed", "preparing", "ready", "completed"]:
            response = set_status(client, order, new_status)
            assert response.status_code == 200
            assert response.data["status"] == new_status

        # The customer hears about "confirmed" and "ready", not about every step.
        assert Notification.objects.filter(user=customer, type="order").count() == 2

    def test_a_step_cannot_be_skipped(self, as_user, staff_user, make_order):
        order = make_order()

        response = set_status(as_user(staff_user), order, "ready")

        assert response.status_code == 409
        assert response.data["code"] == "CONFLICT"

    def test_customers_cannot_change_the_status(self, as_user, customer, make_order):
        order = make_order(customer)

        response = set_status(as_user(customer), order, "confirmed")

        assert response.status_code == 403

    def test_an_unknown_status_is_rejected(self, as_user, staff_user, make_order):
        order = make_order()

        response = set_status(as_user(staff_user), order, "nonsense")

        assert response.status_code == 400
        assert "status" in response.data["errors"]

    @pytest.mark.parametrize("final", [OrderStatus.COMPLETED, OrderStatus.CANCELLED])
    def test_finished_orders_are_frozen(self, as_user, staff_user, make_order, final):
        order = make_order(status=final)

        response = set_status(as_user(staff_user), order, "confirmed")

        assert response.status_code == 409


class TestCancellation:
    def test_a_customer_cancels_their_own_pending_order(
        self, as_user, customer, staff_user, make_order
    ):
        order = make_order(customer)

        response = as_user(customer).post(f"{URL}{order.pk}/cancel/")

        assert response.status_code == 200
        assert response.data["status"] == "cancelled"
        assert Notification.objects.filter(
            user=staff_user, message__contains="cancelled by the customer"
        ).exists()

    def test_a_customer_cannot_cancel_once_it_is_confirmed(self, as_user, customer, make_order):
        order = make_order(customer, status=OrderStatus.CONFIRMED)

        response = as_user(customer).post(f"{URL}{order.pk}/cancel/")

        assert response.status_code == 409

    def test_a_customer_cannot_cancel_someone_elses_order(
        self, as_user, customer, create_user, make_order
    ):
        foreign = make_order(create_user(email="other@example.com"))

        response = as_user(customer).post(f"{URL}{foreign.pk}/cancel/")

        assert response.status_code == 404

    def test_staff_can_cancel_an_order_in_preparation(
        self, as_user, staff_user, customer, make_order
    ):
        order = make_order(customer, status=OrderStatus.PREPARING)

        response = set_status(as_user(staff_user), order, "cancelled")

        assert response.status_code == 200
        assert Notification.objects.filter(
            user=customer, message__contains="cancelled by the restaurant"
        ).exists()

    def test_an_order_that_is_ready_can_no_longer_be_cancelled(
        self, as_user, staff_user, make_order
    ):
        order = make_order(status=OrderStatus.READY)

        response = set_status(as_user(staff_user), order, "cancelled")

        assert response.status_code == 409


class TestTableSynchronisation:
    def test_the_table_is_cleaned_only_after_its_last_open_order(
        self, as_user, staff_user, make_order, table
    ):
        table.status = TableStatus.OCCUPIED
        table.save()
        first = make_order(order_type=OrderType.DINE_IN, status=OrderStatus.READY, table=table)
        second = make_order(order_type=OrderType.DINE_IN, status=OrderStatus.READY, table=table)
        client = as_user(staff_user)

        set_status(client, first, "completed")
        table.refresh_from_db()
        still_occupied = table.status

        set_status(client, second, "completed")
        table.refresh_from_db()

        assert still_occupied == TableStatus.OCCUPIED
        assert table.status == TableStatus.CLEANING

    def test_cancelling_an_order_leaves_the_table_alone(
        self, as_user, staff_user, make_order, table
    ):
        table.status = TableStatus.OCCUPIED
        table.save()
        order = make_order(order_type=OrderType.DINE_IN, table=table)

        set_status(as_user(staff_user), order, "cancelled")

        table.refresh_from_db()
        assert table.status == TableStatus.OCCUPIED