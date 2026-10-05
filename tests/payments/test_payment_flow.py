from decimal import Decimal

import pytest
from django.utils import timezone

from apps.invoices.models import Invoice
from apps.notifications.models import Notification
from apps.orders.models import OrderStatus
from apps.payments.models import Payment, PaymentMethod, PaymentStatus

URL = "/api/payments/"
TOKEN_OK = "tok_visa"
TOKEN_DECLINED = "tok_declined"

pytestmark = pytest.mark.django_db


def pay(client, order, method="card", **extra):
    payload = {"order": order.pk, "method": method}
    payload.update(extra)
    return client.post(URL, payload, format="json")


def existing_payment(order, status, method=PaymentMethod.CASH):
    paid_at = timezone.now() if status == PaymentStatus.PAID else None
    return Payment.objects.create(
        order=order, method=method, amount=order.total, status=status, paid_at=paid_at
    )


class TestStartingPayments:
    def test_a_cash_payment_waits_for_staff_and_ignores_client_fields(
        self, as_user, customer, staff_user, order
    ):
        response = pay(as_user(customer), order, "cash", amount="0.01", status="paid")

        assert response.status_code == 201
        assert response.data["status"] == "pending"
        assert response.data["amount"] == "10.00"
        assert response.data["reference"].startswith("PAY-")
        assert response.data["paid_at"] is None
        assert response.data["currency"] == "USD"
        assert Notification.objects.filter(user=staff_user, type="payment").count() == 1
        assert not Invoice.objects.exists()

    def test_an_approved_card_payment_is_paid_and_issues_an_invoice(
        self, as_user, customer, order
    ):
        response = pay(as_user(customer), order, "card", payment_token=TOKEN_OK)

        assert response.status_code == 201
        assert response.data["status"] == "paid"
        assert response.data["paid_at"] is not None
        assert Invoice.objects.filter(order=order).count() == 1
        assert Notification.objects.filter(
            user=customer, type="payment", message__contains="Invoice"
        ).exists()

    def test_a_declined_card_is_recorded_as_failed_without_an_invoice(
        self, as_user, customer, order
    ):
        response = pay(as_user(customer), order, "card", payment_token=TOKEN_DECLINED)

        assert response.status_code == 201
        assert response.data["status"] == "failed"
        assert Payment.objects.get().status == PaymentStatus.FAILED
        assert not Invoice.objects.exists()

    def test_the_customer_can_retry_after_a_decline(self, as_user, customer, order):
        client = as_user(customer)
        pay(client, order, "card", payment_token=TOKEN_DECLINED)

        retry = pay(client, order, "card", payment_token=TOKEN_OK)

        assert retry.data["status"] == "paid"
        assert Payment.objects.count() == 2

    def test_mobile_money_goes_through_the_same_gateway(self, as_user, customer, order):
        response = pay(as_user(customer), order, "mobile_money", payment_token=TOKEN_OK)

        assert response.data["status"] == "paid"

    def test_a_card_payment_needs_a_token(self, as_user, customer, order):
        response = pay(as_user(customer), order, "card")

        assert response.status_code == 400
        assert "payment_token" in response.data["errors"]
        assert Payment.objects.count() == 0

    @pytest.mark.parametrize("existing", [PaymentStatus.PENDING, PaymentStatus.PAID])
    def test_an_order_cannot_have_two_active_payments(
        self, as_user, customer, order, existing
    ):
        existing_payment(order, existing)

        response = pay(as_user(customer), order, "cash")

        assert response.status_code == 409
        assert response.data["code"] == "CONFLICT"

    def test_a_customer_cannot_pay_someone_elses_order(
        self, as_user, customer, create_user, make_order
    ):
        foreign = make_order(create_user(email="other@example.com"))

        response = pay(as_user(customer), foreign, "cash")

        assert response.status_code == 400
        assert "order" in response.data["errors"]

    def test_staff_can_take_a_payment_for_any_order(self, as_user, staff_user, order):
        response = pay(as_user(staff_user), order, "cash")

        assert response.status_code == 201

    def test_a_cancelled_order_cannot_be_paid(self, as_user, customer, make_order):
        cancelled = make_order(customer, status=OrderStatus.CANCELLED)

        response = pay(as_user(customer), cancelled, "cash")

        assert response.status_code == 409

    def test_an_order_with_nothing_to_pay_is_refused(self, as_user, customer, make_order):
        free = make_order(customer, total=Decimal("0.00"))

        response = pay(as_user(customer), free, "cash")

        assert response.status_code == 409

    def test_an_unknown_order_is_refused(self, as_user, customer):
        response = as_user(customer).post(URL, {"order": 9999, "method": "cash"}, format="json")

        assert response.status_code == 400
        assert "order" in response.data["errors"]

    def test_an_unknown_method_is_refused(self, as_user, customer, order):
        response = pay(as_user(customer), order, "bitcoin")

        assert response.status_code == 400
        assert "method" in response.data["errors"]

    def test_anonymous_cannot_pay(self, api_client, order):
        assert pay(api_client, order, "cash").status_code == 401


class TestSettlingPayments:
    def test_staff_confirm_a_cash_payment_and_the_invoice_is_issued(
        self, as_user, staff_user, customer, order
    ):
        created = pay(as_user(customer), order, "cash")

        response = as_user(staff_user).post(f"{URL}{created.data['id']}/confirm/")

        assert response.status_code == 200
        assert response.data["status"] == "paid"
        assert response.data["paid_at"] is not None
        assert Invoice.objects.filter(order=order).count() == 1
        assert Notification.objects.filter(
            user=customer, message__contains="received"
        ).exists()

    def test_customers_cannot_confirm_payments(self, as_user, customer, order):
        created = pay(as_user(customer), order, "cash")

        response = as_user(customer).post(f"{URL}{created.data['id']}/confirm/")

        assert response.status_code == 403

    def test_staff_cannot_confirm_a_card_payment(self, as_user, staff_user, order):
        stuck = existing_payment(order, PaymentStatus.PENDING, PaymentMethod.CARD)

        response = as_user(staff_user).post(f"{URL}{stuck.pk}/confirm/")

        assert response.status_code == 409

    def test_confirming_twice_is_a_conflict_and_issues_one_invoice(
        self, as_user, staff_user, customer, order
    ):
        created = pay(as_user(customer), order, "cash")
        as_user(staff_user).post(f"{URL}{created.data['id']}/confirm/")

        response = as_user(staff_user).post(f"{URL}{created.data['id']}/confirm/")

        assert response.status_code == 409
        assert Invoice.objects.count() == 1

    def test_the_owner_can_cancel_a_pending_payment(self, as_user, customer, order):
        created = pay(as_user(customer), order, "cash")

        response = as_user(customer).post(f"{URL}{created.data['id']}/cancel/")

        assert response.status_code == 200
        assert response.data["status"] == "failed"

    def test_the_order_can_be_paid_again_after_a_cancellation(self, as_user, customer, order):
        client = as_user(customer)
        created = pay(client, order, "cash")
        client.post(f"{URL}{created.data['id']}/cancel/")

        response = pay(client, order, "card", payment_token=TOKEN_OK)

        assert response.data["status"] == "paid"

    def test_a_paid_payment_cannot_be_cancelled(self, as_user, customer, order):
        paid = pay(as_user(customer), order, "card", payment_token=TOKEN_OK)

        response = as_user(customer).post(f"{URL}{paid.data['id']}/cancel/")

        assert response.status_code == 409

    def test_a_customer_cannot_cancel_someone_elses_payment(
        self, as_user, customer, create_user, make_order
    ):
        foreign = make_order(create_user(email="other@example.com"))
        theirs = existing_payment(foreign, PaymentStatus.PENDING)

        response = as_user(customer).post(f"{URL}{theirs.pk}/cancel/")

        assert response.status_code == 404


class TestVisibility:
    def test_customers_only_see_their_own_payments(
        self, as_user, customer, create_user, make_order, order
    ):
        mine = existing_payment(order, PaymentStatus.PENDING)
        existing_payment(make_order(create_user(email="other@example.com")), PaymentStatus.PENDING)

        response = as_user(customer).get(URL)

        assert [item["id"] for item in response.data["results"]] == [mine.pk]

    def test_staff_see_every_payment(
        self, as_user, staff_user, create_user, make_order, order
    ):
        existing_payment(order, PaymentStatus.PENDING)
        existing_payment(make_order(create_user(email="other@example.com")), PaymentStatus.PENDING)

        response = as_user(staff_user).get(URL)

        assert response.data["count"] == 2

    def test_a_foreign_payment_is_not_found(
        self, as_user, customer, create_user, make_order
    ):
        foreign = existing_payment(
            make_order(create_user(email="other@example.com")), PaymentStatus.PENDING
        )

        response = as_user(customer).get(f"{URL}{foreign.pk}/")

        assert response.status_code == 404

    def test_filters_by_status_and_method(self, as_user, staff_user, make_order):
        paid = existing_payment(make_order(), PaymentStatus.PAID, PaymentMethod.CARD)
        existing_payment(make_order(), PaymentStatus.PENDING, PaymentMethod.CASH)
        client = as_user(staff_user)

        by_status = client.get(URL, {"status": "paid"})
        by_method = client.get(URL, {"method": "card"})

        assert [item["id"] for item in by_status.data["results"]] == [paid.pk]
        assert [item["id"] for item in by_method.data["results"]] == [paid.pk]