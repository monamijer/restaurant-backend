"""Read-only aggregations behind the dashboard and the reports.

Sums and counts are done by the database. Anything that depends on the restaurant's local
day or hour is bucketed in Python instead: converting time zones inside SQL needs the
time-zone tables to be loaded into MySQL/MariaDB, and without them it silently yields NULL."""

from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Count, Sum
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.orders import services as order_services
from apps.orders.models import Order, OrderItem, OrderStatus, OrderType
from apps.payments.models import Payment, PaymentStatus
from apps.queue_mgmt import services as queue_services
from apps.reservations import services as reservation_services
from apps.reservations.models import Reservation, ReservationStatus
from apps.tables.models import Table, TableStatus

from .periods import bucket_start, bucket_starts, make_period, previous_period

ZERO = Decimal("0.00")
CENT = Decimal("0.01")
TENTH = Decimal("0.1")
PERCENT = Decimal("100")
MINUTES_PER_HOUR = 60
HOURS_PER_DAY = 24
RECENT_ACTIVITY_LIMIT = 10
DASHBOARD_TOP_ITEMS = 5
UTILISED_RESERVATIONS = (
    ReservationStatus.CONFIRMED,
    ReservationStatus.COMPLETED,
    ReservationStatus.NO_SHOW,
)


# --- Building blocks ----------------------------------------------------------------
def _paid(period):
    return Payment.objects.filter(
        status=PaymentStatus.PAID, paid_at__gte=period.start, paid_at__lt=period.end
    )


def _orders(period):
    return Order.objects.filter(created_at__gte=period.start, created_at__lt=period.end)


def _local_day(moment, period):
    return moment.astimezone(period.zone).date()


def _average(revenue, count):
    return (revenue / count).quantize(CENT, rounding=ROUND_HALF_UP) if count else ZERO


def _minutes(wall_time):
    return wall_time.hour * MINUTES_PER_HOUR + wall_time.minute


def percent_change(current, previous):
    """Variation in percent against the previous period; None when there is nothing to compare."""
    previous = Decimal(previous)
    if previous == 0:
        return None
    return float(((Decimal(current) - previous) / previous * PERCENT).quantize(TENTH, ROUND_HALF_UP))


# --- Totals -------------------------------------------------------------------------
def revenue_totals(period):
    data = _paid(period).aggregate(revenue=Sum("amount"), payments=Count("id"))
    revenue, payments = data["revenue"] or ZERO, data["payments"]
    return {
        "revenue": revenue,
        "paid_orders": payments,
        "average_order_value": _average(revenue, payments),
    }


def order_count(period):
    return _orders(period).exclude(status=OrderStatus.CANCELLED).count()


def new_customers(period):
    return User.objects.filter(
        role=Role.CLIENT, created_at__gte=period.start, created_at__lt=period.end
    ).count()


# --- Series -------------------------------------------------------------------------
def revenue_series(period, group_by="day"):
    buckets = {start: [ZERO, 0] for start in bucket_starts(period, group_by)}
    for paid_at, amount in _paid(period).values_list("paid_at", "amount"):
        bucket = buckets[bucket_start(_local_day(paid_at, period), group_by)]
        bucket[0] += amount
        bucket[1] += 1
    return [
        {
            "period": start,
            "revenue": revenue,
            "orders": count,
            "average_order_value": _average(revenue, count),
        }
        for start, (revenue, count) in buckets.items()
    ]


def order_volume_series(period, group_by="day"):
    rows = {
        start: {"total": 0, "dine_in": 0, "takeaway": 0, "delivery": 0, "cancelled": 0}
        for start in bucket_starts(period, group_by)
    }
    for created_at, order_type, status in _orders(period).values_list(
        "created_at", "order_type", "status"
    ):
        row = rows[bucket_start(_local_day(created_at, period), group_by)]
        if status == OrderStatus.CANCELLED:
            row["cancelled"] += 1
            continue
        row["total"] += 1
        row[order_type] += 1
    return [{"period": start, **row} for start, row in rows.items()]


def top_items(period, limit):
    rows = (
        OrderItem.objects.filter(order__created_at__gte=period.start, order__created_at__lt=period.end)
        .exclude(order__status=OrderStatus.CANCELLED)
        .values("menu_item_id", "menu_item__name")
        .annotate(quantity=Sum("quantity"), revenue=Sum("subtotal"))
        .order_by("-quantity", "-revenue", "menu_item__name")[:limit]
    )
    return [
        {
            "menu_item": row["menu_item_id"],
            "name": row["menu_item__name"],
            "quantity": row["quantity"],
            "revenue": row["revenue"],
        }
        for row in rows
    ]


def peak_hours(period):
    """Orders placed (and their value) for each local hour of the day."""
    hours = {hour: [0, ZERO] for hour in range(HOURS_PER_DAY)}
    orders = _orders(period).exclude(status=OrderStatus.CANCELLED)
    for created_at, total in orders.values_list("created_at", "total"):
        bucket = hours[created_at.astimezone(period.zone).hour]
        bucket[0] += 1
        bucket[1] += total
    return [{"hour": hour, "orders": count, "revenue": value} for hour, (count, value) in hours.items()]


def table_utilization(period, restaurant):
    """Per table: booked minutes against opening minutes, plus dine-in activity."""
    open_minutes = _minutes(restaurant.closing_time) - _minutes(restaurant.opening_time)
    available_minutes = period.days * open_minutes
    rows = {
        table.pk: {
            "table": table.pk,
            "number": table.number,
            "capacity": table.capacity,
            "reservations": 0,
            "reserved_minutes": 0,
            "utilisation_percent": 0.0,
            "dine_in_orders": 0,
            "orders_value": ZERO,
        }
        for table in Table.objects.order_by("number")
    }
    booked = Reservation.objects.filter(
        status__in=UTILISED_RESERVATIONS, starts_at__gte=period.start, starts_at__lt=period.end
    ).values_list("table_id", "starts_at", "ends_at")
    for table_id, starts_at, ends_at in booked:
        rows[table_id]["reservations"] += 1
        rows[table_id]["reserved_minutes"] += int((ends_at - starts_at).total_seconds() // MINUTES_PER_HOUR)

    dine_in = (
        _orders(period)
        .filter(order_type=OrderType.DINE_IN, table__isnull=False)
        .exclude(status=OrderStatus.CANCELLED)
        .values_list("table_id", "total")
    )
    for table_id, total in dine_in:
        rows[table_id]["dine_in_orders"] += 1
        rows[table_id]["orders_value"] += total

    for row in rows.values():
        if available_minutes:
            share = row["reserved_minutes"] / available_minutes * 100
            row["utilisation_percent"] = round(min(100.0, share), 1)
    return list(rows.values())


def payments_listing(period):
    """Every payment created during the period, with local timestamps, for the CSV export."""
    rows = []
    payments = Payment.objects.filter(created_at__gte=period.start, created_at__lt=period.end)
    for payment in payments.order_by("created_at", "pk"):
        paid_at = payment.paid_at
        rows.append(
            {
                "reference": payment.reference,
                "order": payment.order_id,
                "method": payment.method,
                "status": payment.status,
                "amount": payment.amount,
                "created_at": payment.created_at.astimezone(period.zone).isoformat(timespec="minutes"),
                "paid_at": paid_at.astimezone(period.zone).isoformat(timespec="minutes") if paid_at else "",
            }
        )
    return rows


# --- Dashboard ----------------------------------------------------------------------
def _kpi(current, previous):
    return {"value": current, "previous": previous, "change_percent": percent_change(current, previous)}


def live_snapshot(restaurant, now):
    """What is happening right now, whatever period the dashboard shows."""
    today = now.astimezone(restaurant.zone).date()
    day = make_period(restaurant, today, today)
    status_counts = dict(Table.objects.values_list("status").annotate(count=Count("id")))
    total_tables = sum(status_counts.values())
    occupied = status_counts.get(TableStatus.OCCUPIED, 0)
    return {
        "reservations_today": Reservation.objects.filter(
            reservation_services.blocking(now), starts_at__gte=day.start, starts_at__lt=day.end
        ).count(),
        "pending_reservations": Reservation.objects.filter(
            status=ReservationStatus.PENDING, expires_at__gt=now
        ).count(),
        "queue_waiting": len(queue_services.waiting_positions()),
        "orders_in_progress": Order.objects.filter(status__in=order_services.OPEN_STATUSES).count(),
        "pending_payments": Payment.objects.filter(status=PaymentStatus.PENDING).count(),
        "tables": {
            "total": total_tables,
            "available": status_counts.get(TableStatus.AVAILABLE, 0),
            "occupied": occupied,
            "reserved": status_counts.get(TableStatus.RESERVED, 0),
            "cleaning": status_counts.get(TableStatus.CLEANING, 0),
            "occupancy_percent": round(occupied / total_tables * 100, 1) if total_tables else 0.0,
        },
    }


def recent_activity(limit=RECENT_ACTIVITY_LIMIT):
    events = []
    for order in Order.objects.order_by("-created_at")[:limit]:
        events.append(
            {"type": "order", "id": order.pk, "at": order.created_at, "status": order.status, "amount": order.total}
        )
    for reservation in Reservation.objects.order_by("-created_at")[:limit]:
        events.append(
            {"type": "reservation", "id": reservation.pk, "at": reservation.created_at,
             "status": reservation.status, "amount": None}
        )
    for payment in Payment.objects.filter(status=PaymentStatus.PAID).order_by("-paid_at")[:limit]:
        events.append(
            {"type": "payment", "id": payment.pk, "at": payment.paid_at,
             "status": payment.status, "amount": payment.amount}
        )
    events.sort(key=lambda event: event["at"], reverse=True)
    return events[:limit]


def build_stats(restaurant, period, now=None):
    now = now or timezone.now()
    before = previous_period(restaurant, period)
    current, previous = revenue_totals(period), revenue_totals(before)
    return {
        "period": {"start": period.start_day, "end": period.end_day, "days": period.days},
        "kpis": {
            "revenue": _kpi(current["revenue"], previous["revenue"]),
            "orders": _kpi(order_count(period), order_count(before)),
            "average_order_value": _kpi(current["average_order_value"], previous["average_order_value"]),
            "new_customers": _kpi(new_customers(period), new_customers(before)),
        },
        "customers_total": User.objects.filter(role=Role.CLIENT, is_active=True).count(),
        "today": live_snapshot(restaurant, now),
        "revenue_over_time": revenue_series(period),
        "orders_over_time": order_volume_series(period),
        "top_items": top_items(period, DASHBOARD_TOP_ITEMS),
        "recent_activity": recent_activity(),
    }