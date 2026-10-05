"""Order business rules: server-side pricing, order-type rules and the status machine.

Pricing
-------
The client sends dishes and quantities only. Names, unit prices, the tax rate and every
total are computed here from the database and frozen on the order, so later menu or tax
changes never rewrite history.

Concurrency
-----------
Creating a dine-in order locks only the table. Completing one locks the table first and the
order second. Every other change locks only the order. Because a table is always locked
before any order row, no two paths can end up waiting on each other.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.accounts.permissions import STAFF_ROLES
from apps.core.api import ConflictError
from apps.core.models import RestaurantSettings
from apps.menu.models import MenuItem
from apps.notifications import services as notifications
from apps.notifications.models import NotificationType
from apps.tables import services as table_services
from apps.tables.models import Table, TableStatus

from .models import Order, OrderItem, OrderStatus, OrderType
from apps.core.fields import CURRENCY_CODE
from apps.payments import services as payment_services

CENT = Decimal("0.01")
ONE_HUNDRED = Decimal("100")

OPEN_STATUSES = (
    OrderStatus.PENDING,
    OrderStatus.CONFIRMED,
    OrderStatus.PREPARING,
    OrderStatus.READY,
)

ALLOWED_TRANSITIONS = {
    OrderStatus.PENDING: {OrderStatus.CONFIRMED, OrderStatus.CANCELLED},
    OrderStatus.CONFIRMED: {OrderStatus.PREPARING, OrderStatus.CANCELLED},
    OrderStatus.PREPARING: {OrderStatus.READY, OrderStatus.CANCELLED},
    OrderStatus.READY: {OrderStatus.COMPLETED},
}


# --- Pricing ------------------------------------------------------------------------
def compute_tax(subtotal, tax_rate):
    return (subtotal * tax_rate / ONE_HUNDRED).quantize(CENT, rounding=ROUND_HALF_UP)


def _type_errors(order_type, table_id, delivery_address, contact_phone):
    errors = {}
    if order_type == OrderType.DINE_IN and table_id is None:
        errors["table"] = ["A dine-in order needs a table."]
    if order_type != OrderType.DINE_IN and table_id is not None:
        errors["table"] = ["Only dine-in orders use a table."]
    if order_type == OrderType.DELIVERY:
        if not delivery_address.strip():
            errors["delivery_address"] = ["A delivery order needs an address."]
        if not contact_phone.strip():
            errors["contact_phone"] = ["A delivery order needs a contact phone."]
    return errors


def _dish_error(dish):
    """Error for one order line, in the same shape DRF uses for nested serializers."""
    if dish is None:
        return {"menu_item": ["This dish does not exist."]}
    if not dish.is_available:
        return {"menu_item": [f"'{dish.name}' is not available."]}
    return {}


# --- Creation -----------------------------------------------------------------------
def create_order(
    *,
    customer,
    order_type,
    lines,
    table_id=None,
    delivery_address="",
    contact_phone="",
    notes="",
    restaurant=None,
):
    """Create an order from [{menu_item_id, quantity, special_instructions}] lines."""
    restaurant = restaurant or RestaurantSettings.load()
    dishes = MenuItem.objects.in_bulk({line["menu_item_id"] for line in lines})

    errors = _type_errors(order_type, table_id, delivery_address, contact_phone)
    line_errors = [_dish_error(dishes.get(line["menu_item_id"])) for line in lines]
    if any(line_errors):
        errors["items"] = line_errors
    if errors:
        raise ValidationError(errors)

    priced = [
        {
            "dish": dishes[line["menu_item_id"]],
            "quantity": line["quantity"],
            "subtotal": dishes[line["menu_item_id"]].price * line["quantity"],
            "instructions": line.get("special_instructions", ""),
        }
        for line in lines
    ]
    subtotal = sum((entry["subtotal"] for entry in priced), Decimal("0.00"))
    tax_amount = compute_tax(subtotal, restaurant.tax_rate)

    with transaction.atomic():
        table = None
        if table_id is not None:
            table = Table.objects.select_for_update().filter(pk=table_id).first()
            if table is None:
                raise ValidationError({"table": ["Unknown table."]})

        order = Order.objects.create(
            customer=customer,
            table=table,
            order_type=order_type,
            status=OrderStatus.PENDING,
            delivery_address=delivery_address.strip() if order_type == OrderType.DELIVERY else "",
            contact_phone=contact_phone,
            notes=notes,
            subtotal=subtotal,
            tax_rate=restaurant.tax_rate,
            tax_amount=tax_amount,
            total=subtotal + tax_amount,
        )
        OrderItem.objects.bulk_create(
            [
                OrderItem(
                    order=order,
                    menu_item=entry["dish"],
                    item_name=entry["dish"].name,
                    quantity=entry["quantity"],
                    unit_price=entry["dish"].price,
                    subtotal=entry["subtotal"],
                    special_instructions=entry["instructions"],
                )
                for entry in priced
            ]
        )
        if table is not None and table.status != TableStatus.OCCUPIED:
            table_services.set_table_status(table, TableStatus.OCCUPIED)

        notifications.notify_staff(
            NotificationType.ORDER,
            f"New {order.get_order_type_display().lower()} order #{order.pk}: "
            f"{len(priced)} line(s), {order.total} {CURRENCY_CODE}.",
        )
    return order


# --- Status changes -----------------------------------------------------------------
def _check_actor(order, new_status, actor):
    """A customer may only cancel their own order, and only while it is pending."""
    if actor is None or actor.role in STAFF_ROLES:
        return
    if order.customer_id != actor.pk:
        # Defence in depth: the view already scopes the queryset to the owner.
        raise PermissionDenied()
    if order.status != OrderStatus.PENDING:
        raise ConflictError("A customer can only cancel an order while it is pending.")


def _table_has_no_open_order(table_id):
    """Locking read: it sees the latest committed statuses, not the transaction snapshot."""
    open_orders = (
        Order.objects.select_for_update()
        .filter(table_id=table_id, order_type=OrderType.DINE_IN, status__in=OPEN_STATUSES)
        .values_list("pk", flat=True)[:1]
    )
    return not list(open_orders)

def _check_money(order, new_status):
    """Only a fully paid order is completed; a paid order cannot simply be cancelled."""
    paid = payment_services.paid_total(order.pk)
    if new_status == OrderStatus.COMPLETED and paid < order.total:
        raise ConflictError("The order is not fully paid.")
    if new_status == OrderStatus.CANCELLED:
        if paid > 0:
            raise ConflictError("A paid order cannot be cancelled: refund it first.")
        payment_services.fail_pending_payments(order.pk)

def _notify_customer(order, new_status, actor):
    owner_cancelled = actor is not None and order.customer_id == actor.pk
    if new_status == OrderStatus.CANCELLED and owner_cancelled:
        notifications.notify_staff(
            NotificationType.ORDER, f"Order #{order.pk} was cancelled by the customer."
        )
        return
    if order.customer_id is None:
        return
    messages = {
        OrderStatus.CONFIRMED: f"Your order #{order.pk} has been confirmed.",
        OrderStatus.READY: f"Your order #{order.pk} is ready.",
        OrderStatus.CANCELLED: f"Your order #{order.pk} was cancelled by the restaurant.",
    }
    if new_status in messages:
        notifications.notify(order.customer, NotificationType.ORDER, messages[new_status])


def _move(order_id, new_status, *, actor=None):
    # Unlocked read, taken before the transaction: a table never changes for a given order.
    table_id = Order.objects.filter(pk=order_id).values_list("table_id", flat=True).first()
    with transaction.atomic():
        table = None
        if new_status == OrderStatus.COMPLETED and table_id is not None:
            # Lock order: table first, then order, so completions on one table are serialised.
            table = Table.objects.select_for_update().filter(pk=table_id).first()

        order = Order.objects.select_for_update().get(pk=order_id)
        _check_actor(order, new_status, actor)
        if new_status not in ALLOWED_TRANSITIONS.get(order.status, set()):
            raise ConflictError(
                f"An order that is '{order.status!s}' cannot become '{new_status!s}'."
            )
        _check_money(order, new_status)        
        order.status = new_status
        order.save(update_fields=["status", "updated_at"])

        if table is not None and _table_has_no_open_order(table.pk):
            table_services.set_table_status(table, TableStatus.CLEANING)

        _notify_customer(order, new_status, actor)
    return order


def update_status(order_id, new_status):
    """Staff-driven change, including cancellation by the restaurant."""
    return _move(order_id, new_status)


def cancel_order(order_id, *, actor):
    """Cancellation requested by `actor`: a customer (own pending orders) or staff."""
    return _move(order_id, OrderStatus.CANCELLED, actor=actor)