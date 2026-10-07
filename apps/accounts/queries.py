from decimal import Decimal

from django.db.models import Count, DecimalField, Max, Q, Sum, Value
from django.db.models.functions import Coalesce

from apps.orders.models import OrderStatus
from apps.payments.models import PaymentStatus

from .models import User

NOT_CANCELLED = ~Q(orders__status=OrderStatus.CANCELLED)


def users_with_customer_stats():
    """Every user with order count, amount paid and last order, computed in one query."""
    return User.objects.annotate(
        orders_count=Count("orders", filter=NOT_CANCELLED, distinct=True),
        total_spent=Coalesce(
            Sum("orders__payments__amount", filter=Q(orders__payments__status=PaymentStatus.PAID)),
            Value(Decimal("0.00")),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        ),
        last_order_at=Max("orders__created_at", filter=NOT_CANCELLED),
    )