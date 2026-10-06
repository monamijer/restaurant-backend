"""Builds the demo restaurant through the real services.

Every state change goes through the same services the API uses, so invoices are numbered,
totals are exact and notifications exist. History is created oldest first, with the clock
frozen at the moment each event is supposed to have happened."""

import random
from datetime import datetime, time, timedelta

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Role
from apps.core.api import ConflictError
from apps.core.models import RestaurantSettings
from apps.invoices.models import Invoice, InvoiceSequence
from apps.menu.models import Category, MenuItem
from apps.notifications.models import Notification
from apps.orders import services as order_services
from apps.orders.models import Order, OrderStatus, OrderType
from apps.payments import services as payment_services
from apps.payments.gateways import ChargeResult
from apps.payments.models import PaymentMethod
from apps.queue_mgmt import services as queue_services
from apps.queue_mgmt.models import QueueTicket
from apps.reservations import services as reservation_services
from apps.reservations.models import Reservation, ReservationStatus
from apps.tables import services as table_services
from apps.tables.models import Table, TableStatus

from . import catalog
from .clock import frozen_at
from .images import placeholder_image
from .people import demo_accounts

DEMO_TOKEN = "tok_demo"
PENDING_HOLD_BEFORE_START = timedelta(hours=1)
RECENT_NOTIFICATION_WINDOW = timedelta(hours=2)

# Local service times: a lunch rush and a dinner rush, every quarter of an hour.
LUNCH_TIMES = [time(12, minute) for minute in (0, 15, 30, 45)] + [
    time(13, minute) for minute in (0, 15, 30, 45)
]
DINNER_TIMES = [time(18, 30), time(18, 45)] + [
    time(hour, minute) for hour in (19, 20) for minute in (0, 15, 30, 45)
]
SERVICE_TIMES = LUNCH_TIMES + DINNER_TIMES
RESERVATION_STARTS = [time(12, 30), time(19, 0), time(20, 0)]
RESERVATION_DURATIONS = [60, 90, 120]

# Statuses that keep a table busy at the time they cover, history included.
OCCUPYING_RESERVATIONS = (
    ReservationStatus.PENDING,
    ReservationStatus.CONFIRMED,
    ReservationStatus.COMPLETED,
    ReservationStatus.NO_SHOW,
)


class _ApprovingGateway:
    """The seed never depends on the application's payment-gateway settings."""

    def charge(self, *, method, amount, token, reference):
        return ChargeResult(approved=True)


def wipe():
    """Delete every restaurant record and the demo accounts. Other accounts are kept."""
    with transaction.atomic():
        for invoice in Invoice.objects.all():
            invoice.pdf_file.delete(save=False)
        Invoice.objects.all().delete()
        Order.objects.all().delete()  # Items are removed with their order.
        Reservation.objects.all().delete()
        QueueTicket.objects.all().delete()
        Notification.objects.all().delete()
        MenuItem.objects.all().delete()
        Category.objects.all().delete()
        Table.objects.all().delete()
        InvoiceSequence.objects.all().delete()
        demo_accounts().delete()


class DemoBuilder:
    def __init__(self, people, *, seed, with_images=True, log=lambda message: None):
        self.rng = random.Random(seed)
        self.people = people
        self.admin = people[Role.ADMIN][0]
        self.staff = people[Role.STAFF][0]
        self.clients = people[Role.CLIENT]
        self.with_images = with_images
        self.log = log
        self.restaurant = None
        self.tables = []
        self.dishes = []
        self.today = None

    # --- Setup ----------------------------------------------------------------------
    def configure_restaurant(self):
        restaurant = RestaurantSettings.load()
        restaurant.name = catalog.RESTAURANT_NAME
        restaurant.timezone = catalog.RESTAURANT_TIMEZONE
        restaurant.tax_rate = catalog.RESTAURANT_TAX_RATE
        restaurant.save()
        self.restaurant = restaurant
        self.today = timezone.now().astimezone(restaurant.zone).date()

    def create_catalogue(self):
        colours = dict(catalog.CATEGORIES)
        categories = {}
        for order, (name, _) in enumerate(catalog.CATEGORIES):
            categories[name] = Category.objects.create(name=name, display_order=order)

        for (category, name, description, price, prep, allergens, calories, featured, available) in catalog.MENU:
            dish = MenuItem.objects.create(
                category=categories[category],
                name=name,
                description=description,
                price=price,
                preparation_time=prep,
                allergens=allergens,
                calories=calories,
                is_featured=featured,
                is_available=available,
            )
            if self.with_images:
                picture = placeholder_image(name, colours[category])
                dish.image.save(f"{dish.slug}.jpg", ContentFile(picture), save=True)
            self.dishes.append(dish)

        for number, capacity, location in catalog.TABLES:
            self.tables.append(Table.objects.create(number=number, capacity=capacity, location=location))
        self.log(f"Catalogue: {len(self.dishes)} dishes, {len(self.tables)} tables")

    # --- Helpers --------------------------------------------------------------------
    def _moment(self, days_ago, wall_time):
        """A UTC instant for a local wall-clock time `days_ago` days back."""
        day = self.today - timedelta(days=days_ago)
        moment = reservation_services.local_wall_to_utc(day, wall_time, self.restaurant.zone)
        if moment is None:  # The local time falls in a daylight-saving gap: use the next hour.
            moment = reservation_services.local_wall_to_utc(
                day, wall_time.replace(hour=wall_time.hour + 1), self.restaurant.zone
            )
        return moment

    def _orderable_dishes(self):
        return [dish for dish in self.dishes if dish.is_available]

    def _random_lines(self):
        picked = self.rng.sample(self._orderable_dishes(), k=self.rng.choice([1, 2, 2, 3, 3, 4]))
        return [
            {
                "menu_item_id": dish.pk,
                "quantity": self.rng.choice([1, 1, 2, 3]),
                "special_instructions": "",
            }
            for dish in picked
        ]

    def _order_details(self, order_type):
        if order_type == OrderType.DINE_IN:
            return {"table_id": self.rng.choice(self.tables).pk}
        if order_type == OrderType.DELIVERY:
            return {
                "delivery_address": self.rng.choice(catalog.DELIVERY_ADDRESSES),
                "contact_phone": f"+2577900{self.rng.randint(1000, 9999)}",
            }
        return {}

    def _pay(self, order, method):
        if method == PaymentMethod.CASH:
            payment = payment_services.start_payment(
                order_id=order.pk, method=method, actor=self.staff
            )
            payment_services.confirm_cash_payment(payment.pk)
        else:
            payment_services.start_payment(
                order_id=order.pk,
                method=method,
                token=DEMO_TOKEN,
                actor=order.customer or self.staff,
                gateway=_ApprovingGateway(),
            )

    # --- Order history --------------------------------------------------------------
    def _seed_one_order(self, moment):
        order_type = self.rng.choices(
            [OrderType.DINE_IN, OrderType.TAKEAWAY, OrderType.DELIVERY], weights=[55, 30, 15]
        )[0]
        customer = self.rng.choice(self.clients + [None, None])  # None: entered by staff
        with frozen_at(moment):
            order = order_services.create_order(
                customer=customer,
                order_type=order_type,
                lines=self._random_lines(),
                restaurant=self.restaurant,
                **self._order_details(order_type),
            )

        if self.rng.random() < 0.06:  # A few orders are cancelled before the kitchen starts.
            with frozen_at(moment + timedelta(minutes=5)):
                order_services.update_status(order.pk, OrderStatus.CANCELLED)
            return

        for minutes, status in ((3, OrderStatus.CONFIRMED), (8, OrderStatus.PREPARING), (25, OrderStatus.READY)):
            with frozen_at(moment + timedelta(minutes=minutes)):
                order_services.update_status(order.pk, status)
        method = self.rng.choices(
            [PaymentMethod.CASH, PaymentMethod.CARD, PaymentMethod.MOBILE_MONEY], weights=[50, 35, 15]
        )[0]
        with frozen_at(moment + timedelta(minutes=35)):
            self._pay(order, method)
        with frozen_at(moment + timedelta(minutes=37)):
            order_services.update_status(order.pk, OrderStatus.COMPLETED)

    def seed_order_history(self, days, per_day):
        for days_ago in range(days, 0, -1):  # Oldest first, so invoice numbers follow time.
            times = sorted(self.rng.choices(SERVICE_TIMES, k=per_day))
            for wall_time in times:
                self._seed_one_order(self._moment(days_ago, wall_time))
            if days_ago % 10 == 0:
                self.log(f"History: {days_ago} days to go")

    # --- Reservations ---------------------------------------------------------------
    def _free_table(self, party_size, starts_at, ends_at):
        busy = set(
            Reservation.objects.filter(
                status__in=OCCUPYING_RESERVATIONS, starts_at__lt=ends_at, ends_at__gt=starts_at
            ).values_list("table_id", flat=True)
        )
        candidates = [t for t in self.tables if t.capacity >= party_size and t.pk not in busy]
        return self.rng.choice(candidates) if candidates else None

    def _book(self, *, days_offset, created_at, hold_open=False):
        """Request one reservation. `days_offset` is relative to today (negative = past)."""
        start_time = self.rng.choice(RESERVATION_STARTS)
        duration = self.rng.choice(RESERVATION_DURATIONS)
        party_size = self.rng.randint(2, 6)
        client = self.rng.choice(self.clients)
        day = self.today + timedelta(days=days_offset)
        starts_at, ends_at = reservation_services.build_window(
            self.restaurant, day, start_time, duration
        )
        table = self._free_table(party_size, starts_at, ends_at)
        if table is None:
            return None, None
        with frozen_at(created_at or timezone.now()):
            try:
                reservation = reservation_services.create_reservation(
                    customer=client,
                    table_id=table.pk,
                    starts_at=starts_at,
                    ends_at=ends_at,
                    party_size=party_size,
                    restaurant=self.restaurant,
                )
            except ConflictError:
                return None, None
        if hold_open:
            # Keep demo requests pending for as long as they are useful to the staff.
            Reservation.objects.filter(pk=reservation.pk).update(
                expires_at=starts_at - PENDING_HOLD_BEFORE_START
            )
        return reservation, client

    def seed_reservation_history(self, days):
        for days_ago in range(days, 0, -1):
            for _ in range(self.rng.choice([1, 2])):
                probe_start = self._moment(days_ago, time(12, 0))
                created_at = probe_start - timedelta(hours=20)
                reservation, client = self._book(days_offset=-days_ago, created_at=created_at)
                if reservation is None:
                    continue
                self._settle_historic_reservation(reservation, client, created_at)

    def _settle_historic_reservation(self, reservation, client, created_at):
        outcome = self.rng.choices(
            ["completed", "no_show", "rejected", "cancelled"], weights=[70, 10, 10, 10]
        )[0]
        decided_at = created_at + timedelta(minutes=10)  # Inside the pending hold.
        if outcome == "rejected":
            with frozen_at(decided_at):
                reservation_services.reject_reservation(reservation.pk)
            return
        if outcome == "cancelled":
            with frozen_at(created_at + timedelta(hours=2)):
                reservation_services.cancel_reservation(reservation.pk, actor=client)
            return
        with frozen_at(decided_at):
            reservation_services.confirm_reservation(reservation.pk)
        if outcome == "completed":
            with frozen_at(reservation.ends_at):
                reservation_services.complete_reservation(reservation.pk)
        else:
            with frozen_at(reservation.starts_at + timedelta(minutes=20)):
                reservation_services.mark_no_show(reservation.pk)

    def seed_future_reservations(self, count=6):
        for index in range(count):
            reservation, _ = self._book(
                days_offset=self.rng.randint(1, 6), created_at=None, hold_open=True
            )
            if reservation is not None and index % 2 == 0:
                reservation_services.confirm_reservation(reservation.pk)

    # --- Live state (today) ---------------------------------------------------------
    def seed_queue(self):
        first, second, third, fourth = self.clients[:4]
        ticket_one = queue_services.join_queue(
            customer=first, name=first.full_name, phone=first.phone, party_size=2
        )
        queue_services.join_queue(customer=None, name="Famille Nkurunziza", phone="", party_size=5)
        queue_services.join_queue(
            customer=second, name=second.full_name, phone=second.phone, party_size=3
        )
        ticket_four = queue_services.join_queue(
            customer=third, name=third.full_name, phone=third.phone, party_size=4
        )
        queue_services.call_next()
        queue_services.seat_ticket(ticket_one.pk)
        queue_services.call_next()
        queue_services.cancel_ticket(ticket_four.pk, actor=third)
        queue_services.join_queue(customer=None, name="Groupe Habonimana", phone="", party_size=6)
        self.log("Queue: waiting, called, seated and cancelled tickets")

    def _live_order(self, *, minutes_ago, order_type, customer, steps, pay=None, **details):
        moment = timezone.now() - timedelta(minutes=minutes_ago)
        with frozen_at(moment):
            order = order_services.create_order(
                customer=customer,
                order_type=order_type,
                lines=self._random_lines(),
                restaurant=self.restaurant,
                **details,
            )
        for offset, status in steps:
            with frozen_at(moment + timedelta(minutes=offset)):
                order_services.update_status(order.pk, status)
        if pay is not None:
            with frozen_at(moment + timedelta(minutes=minutes_ago // 2)):
                self._pay(order, pay)
        return order

    def seed_live_orders(self):
        c = self.clients
        tables = {table.number: table for table in self.tables}
        self._live_order(
            minutes_ago=12, order_type=OrderType.TAKEAWAY, customer=c[0], steps=[]
        )
        self._live_order(
            minutes_ago=30, order_type=OrderType.DINE_IN, customer=c[1],
            steps=[(2, OrderStatus.CONFIRMED)], table_id=tables[4].pk,
        )
        self._live_order(
            minutes_ago=40, order_type=OrderType.DINE_IN, customer=c[2],
            steps=[(2, OrderStatus.CONFIRMED), (8, OrderStatus.PREPARING)], table_id=tables[6].pk,
        )
        self._live_order(
            minutes_ago=50, order_type=OrderType.DELIVERY, customer=c[3],
            steps=[(2, OrderStatus.CONFIRMED), (8, OrderStatus.PREPARING), (25, OrderStatus.READY)],
            pay=PaymentMethod.CARD, delivery_address="Avenue du Lac 14", contact_phone=c[3].phone,
        )
        pending_cash = self._live_order(
            minutes_ago=20, order_type=OrderType.TAKEAWAY, customer=c[4],
            steps=[(2, OrderStatus.CONFIRMED)],
        )
        payment_services.start_payment(
            order_id=pending_cash.pk, method=PaymentMethod.CASH, actor=self.staff
        )
        self.log("Live orders: pending, confirmed, preparing, ready and awaiting cash")

    # --- Wrap-up --------------------------------------------------------------------
    def finalize(self):
        """Bring tables and notifications to a state that matches 'right now'."""
        Table.objects.update(status=TableStatus.AVAILABLE)
        occupied = (
            Order.objects.filter(order_type=OrderType.DINE_IN, status__in=order_services.OPEN_STATUSES)
            .values_list("table_id", flat=True)
        )
        for table in Table.objects.filter(pk__in=set(occupied)):
            table_services.set_table_status(table, TableStatus.OCCUPIED)
        table_services.set_table_status(Table.objects.get(number=9), TableStatus.RESERVED)
        table_services.set_table_status(Table.objects.get(number=10), TableStatus.CLEANING)

        cutoff = timezone.now() - RECENT_NOTIFICATION_WINDOW
        Notification.objects.filter(created_at__lt=cutoff).update(is_read=True)

    def build(self, *, days, per_day):
        self.configure_restaurant()
        self.create_catalogue()
        self.seed_order_history(days, per_day)
        self.seed_reservation_history(days)
        self.seed_future_reservations()
        self.seed_queue()
        self.seed_live_orders()
        self.finalize()