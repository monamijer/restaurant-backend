"""Payment business rules.

Trust model
-----------
The client never states an amount or an outcome. The amount is always the order total, read
from the database, and a payment only becomes `paid` through `settle_payment`, driven by the
gateway's answer (card, mobile money) or by a staff member (cash).

Flow
----
1. `start_payment` (one transaction): lock the order, validate, create a PENDING payment.
2. Card or mobile money: ask the gateway *outside any transaction* (a slow provider must not
   hold database locks), then `settle_payment` applies the answer in a second transaction.
3. Cash: the payment stays PENDING until staff call `confirm_cash_payment`.

Lock order: order row, then payment row, then the invoice counter. Orders take a table lock
before the order row and payments never take one, so the two can never wait on each other.
"""

from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.accounts.permissions import STAFF_ROLES
from apps.core.api import ConflictError
from apps.core.fields import CURRENCY_CODE
from apps.core.models import RestaurantSettings
from apps.invoices import services as invoice_services
from apps.notifications import services as notifications
from apps.notifications.models import NotificationType
from apps.orders.models import Order, OrderStatus

from .gateways import get_gateway
from .models import Payment, PaymentMethod, PaymentStatus

ACTIVE_STATUSES = (PaymentStatus.PENDING, PaymentStatus.PAID)
NO_MONEY = Decimal("0.00")


def paid_total(order_id):
    total = Payment.objects.filter(order_id=order_id, status=PaymentStatus.PAID).aggregate(
        total=Sum("amount")
    )["total"]
    return total or NO_MONEY


def fail_pending_payments(order_id):
    """Call inside the order's row lock, when the order is cancelled."""
    return Payment.objects.filter(order_id=order_id, status=PaymentStatus.PENDING).update(
        status=PaymentStatus.FAILED
    )


def start_payment(*, order_id, method, actor, token="", now=None, gateway=None):
    needs_gateway = method != PaymentMethod.CASH
    if needs_gateway and not token:
        raise ValidationError({"payment_token": ["A payment token is required for this method."]})
    now = now or timezone.now()
    restaurant = RestaurantSettings.load()

    with transaction.atomic():
        order = Order.objects.select_for_update().filter(pk=order_id).first()
        can_pay = order is not None and (
            actor.role in STAFF_ROLES or order.customer_id == actor.pk
        )
        if not can_pay:
            raise ValidationError({"order": ["Unknown order."]})
        if order.status == OrderStatus.CANCELLED:
            raise ConflictError("A cancelled order cannot be paid.")
        if order.total <= NO_MONEY:
            raise ConflictError("This order has nothing to pay.")
        if Payment.objects.filter(order=order, status__in=ACTIVE_STATUSES).exists():
            raise ConflictError("This order already has a pending or completed payment.")

        payment = Payment.objects.create(order=order, method=method, amount=order.total)
        if not needs_gateway:
            notifications.notify_staff(
                NotificationType.PAYMENT,
                f"Cash payment of {payment.amount} {CURRENCY_CODE} is waiting for "
                f"confirmation (order #{order.pk}).",
            )
            return payment

    # Outside any transaction: no database lock is held while the provider answers.
    gateway = gateway or get_gateway()
    result = gateway.charge(
        method=method, amount=payment.amount, token=token, reference=payment.reference
    )
    return settle_payment(payment.pk, approved=result.approved, now=now, restaurant=restaurant)


def _notify_paid(order, payment, invoice):
    if order.customer_id is None:
        return
    invoice_note = f" Invoice {invoice.invoice_number} is available." if invoice else ""
    notifications.notify(
        order.customer,
        NotificationType.PAYMENT,
        f"Payment of {payment.amount} {CURRENCY_CODE} received for order #{order.pk}."
        f"{invoice_note}",
    )


def settle_payment(payment_id, *, approved, now=None, restaurant=None, strict=False):
    """Apply the outcome to a PENDING payment, exactly once.

    A payment that is no longer pending is returned untouched (or refused when `strict`), so
    a retried or duplicated callback can never pay twice or issue a second invoice."""
    now = now or timezone.now()
    restaurant = restaurant or RestaurantSettings.load()
    # Unlocked reads: neither the order of a payment nor the year of `now` ever changes.
    order_id = Payment.objects.filter(pk=payment_id).values_list("order_id", flat=True).first()
    if approved:
        invoice_services.ensure_sequence(now, restaurant)

    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order_id)
        payment = Payment.objects.select_for_update().get(pk=payment_id)
        if payment.status != PaymentStatus.PENDING:
            if strict:
                raise ConflictError(
                    f"A payment that is '{payment.status!s}' cannot be settled."
                )
            return payment

        if not approved:
            payment.status = PaymentStatus.FAILED
            payment.save(update_fields=["status"])
            return payment

        payment.status = PaymentStatus.PAID
        payment.paid_at = now
        payment.save(update_fields=["status", "paid_at"])
        invoice = None
        if paid_total(order.pk) >= order.total:
            invoice = invoice_services.issue_invoice(order, payment, now=now, restaurant=restaurant)
        _notify_paid(order, payment, invoice)
    return payment


def confirm_cash_payment(payment_id, *, now=None):
    method = Payment.objects.filter(pk=payment_id).values_list("method", flat=True).first()
    if method != PaymentMethod.CASH:
        raise ConflictError("Only cash payments are confirmed by staff.")
    return settle_payment(payment_id, approved=True, now=now, strict=True)


def cancel_payment(payment_id, *, actor):
    order_id = Payment.objects.filter(pk=payment_id).values_list("order_id", flat=True).first()
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order_id)
        payment = Payment.objects.select_for_update().get(pk=payment_id)
        if actor.role not in STAFF_ROLES and order.customer_id != actor.pk:
            # Defence in depth: the view already scopes the queryset to the owner.
            raise PermissionDenied()
        if payment.status != PaymentStatus.PENDING:
            raise ConflictError(f"A payment that is '{payment.status!s}' cannot be cancelled.")
        payment.status = PaymentStatus.FAILED
        payment.save(update_fields=["status"])
    return payment