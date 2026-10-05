from datetime import UTC, datetime

import pytest

from apps.invoices.models import Invoice
from apps.payments import services
from apps.payments.models import Payment, PaymentMethod, PaymentStatus
from tests.concurrency_helpers import run_concurrently

ATTEMPTS = 6
YEAR = datetime.now(UTC).year


@pytest.mark.django_db(transaction=True)
def test_simultaneous_payments_get_consecutive_invoice_numbers(create_user, make_order):
    guests = [create_user(email=f"guest{n}@example.com") for n in range(ATTEMPTS)]
    orders = [make_order(guest) for guest in guests]

    outcomes = run_concurrently(
        [
            lambda order=order, guest=guest: services.start_payment(
                order_id=order.pk, method=PaymentMethod.CARD, token="tok_visa", actor=guest
            )
            for order, guest in zip(orders, guests)
        ]
    )

    assert outcomes == ["ok"] * ATTEMPTS
    numbers = sorted(Invoice.objects.values_list("invoice_number", flat=True))
    assert numbers == [f"INV-{YEAR}-{n:06d}" for n in range(1, ATTEMPTS + 1)]


@pytest.mark.django_db(transaction=True)
def test_two_staff_confirming_one_cash_payment_pay_it_once(staff_user, customer, make_order):
    order = make_order(customer)
    payment = services.start_payment(
        order_id=order.pk, method=PaymentMethod.CASH, actor=staff_user
    )

    outcomes = run_concurrently(
        [lambda: services.confirm_cash_payment(payment.pk) for _ in range(2)]
    )

    assert sorted(outcomes) == ["conflict", "ok"]
    assert Payment.objects.get(pk=payment.pk).status == PaymentStatus.PAID
    assert Invoice.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_racing_payment_starts_on_one_order_create_a_single_payment(
    staff_user, customer, make_order
):
    order = make_order(customer)

    outcomes = run_concurrently(
        [
            lambda: services.start_payment(
                order_id=order.pk, method=PaymentMethod.CASH, actor=staff_user
            )
            for _ in range(ATTEMPTS)
        ]
    )

    assert sorted(outcomes) == sorted(["ok"] + ["conflict"] * (ATTEMPTS - 1))
    assert Payment.objects.filter(order=order).count() == 1