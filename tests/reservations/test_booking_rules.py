from datetime import UTC, datetime, time, timedelta
from io import StringIO
from zoneinfo import ZoneInfo

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.core.models import RestaurantSettings
from apps.notifications.models import Notification
from apps.reservations.models import Reservation, ReservationStatus
from apps.tables.models import Table

URL = "/api/reservations/"
LAPSED_BY = timedelta(minutes=1)

pytestmark = pytest.mark.django_db


class TestCreation:
    def test_customer_creates_a_pending_reservation(
        self, as_user, customer, staff_user, booking_payload
    ):
        response = as_user(customer).post(URL, booking_payload(), format="json")

        assert response.status_code == 201
        assert response.data["status"] == "pending"
        assert response.data["table_number"] == 1
        assert response.data["time"] == "19:00"
        assert response.data["duration_minutes"] == 90
        assert response.data["expires_at"] is not None
        assert Notification.objects.filter(user=staff_user, type="reservation").count() == 1

    def test_anonymous_cannot_book(self, api_client, booking_payload):
        response = api_client.post(URL, booking_payload(), format="json")

        assert response.status_code == 401

    @pytest.mark.parametrize(
        ("start", "field"), [("08:30", "time"), ("21:30", "duration_minutes")]
    )
    def test_opening_hours_are_enforced(self, as_user, customer, booking_payload, start, field):
        response = as_user(customer).post(URL, booking_payload(time=start), format="json")

        assert response.status_code == 400
        assert field in response.data["errors"]

    def test_start_must_follow_the_slot_grid(self, as_user, customer, booking_payload):
        response = as_user(customer).post(URL, booking_payload(time="19:15"), format="json")

        assert response.status_code == 400
        assert "time" in response.data["errors"]

    @pytest.mark.parametrize("duration", [0, 15, 45, 210])
    def test_duration_must_respect_the_configured_bounds(
        self, as_user, customer, booking_payload, duration
    ):
        response = as_user(customer).post(
            URL, booking_payload(duration_minutes=duration), format="json"
        )

        assert response.status_code == 400
        assert "duration_minutes" in response.data["errors"]

    def test_cannot_book_in_the_past(self, as_user, customer, booking_payload, booking_day):
        past = (booking_day - timedelta(days=30)).isoformat()

        response = as_user(customer).post(URL, booking_payload(date=past), format="json")

        assert response.status_code == 400
        assert "date" in response.data["errors"]

    def test_party_cannot_exceed_table_capacity(self, as_user, customer, booking_payload):
        response = as_user(customer).post(URL, booking_payload(party_size=5), format="json")

        assert response.status_code == 400
        assert "party_size" in response.data["errors"]

    def test_unknown_table_is_rejected(self, as_user, customer, booking_payload):
        response = as_user(customer).post(URL, booking_payload(table=9999), format="json")

        assert response.status_code == 400
        assert "table" in response.data["errors"]

    def test_times_are_read_in_the_restaurant_timezone(
        self, as_user, customer, booking_payload, booking_day
    ):
        restaurant = RestaurantSettings.load()
        restaurant.timezone = "Europe/Paris"
        restaurant.save()

        response = as_user(customer).post(URL, booking_payload(), format="json")

        expected = datetime.combine(booking_day, time(19, 0), tzinfo=ZoneInfo("Europe/Paris"))
        assert response.status_code == 201
        assert Reservation.objects.get().starts_at == expected.astimezone(UTC)
        assert response.data["time"] == "19:00"


class TestOverlap:
    @pytest.mark.parametrize("start", ["18:00", "19:00", "19:30", "20:00"])
    def test_any_overlap_is_refused_with_409(
        self, as_user, customer, create_user, make_reservation, booking_payload, start
    ):
        make_reservation(create_user(email="owner@example.com"))  # 19:00 to 20:30

        response = as_user(customer).post(URL, booking_payload(time=start), format="json")

        assert response.status_code == 409
        assert response.data["code"] == "CONFLICT"

    @pytest.mark.parametrize(("start", "duration"), [("17:30", 90), ("20:30", 60)])
    def test_back_to_back_bookings_are_allowed(
        self, as_user, customer, create_user, make_reservation, booking_payload, start, duration
    ):
        make_reservation(create_user(email="owner@example.com"))  # 19:00 to 20:30

        response = as_user(customer).post(
            URL, booking_payload(time=start, duration_minutes=duration), format="json"
        )

        assert response.status_code == 201

    def test_another_table_is_unaffected(
        self, as_user, customer, create_user, make_reservation, booking_payload
    ):
        make_reservation(create_user(email="owner@example.com"))
        second_table = Table.objects.create(number=2, capacity=4)

        response = as_user(customer).post(
            URL, booking_payload(table=second_table.pk), format="json"
        )

        assert response.status_code == 201

    def test_a_pending_request_holds_the_slot(
        self, as_user, customer, create_user, booking_payload
    ):
        second_customer = create_user(email="second@example.com")

        first = as_user(customer).post(URL, booking_payload(), format="json")
        second = as_user(second_customer).post(URL, booking_payload(), format="json")

        assert first.status_code == 201
        assert second.status_code == 409

    @pytest.mark.parametrize(
        "released",
        [ReservationStatus.REJECTED, ReservationStatus.CANCELLED, ReservationStatus.EXPIRED],
    )
    def test_finished_reservations_release_the_slot(
        self, as_user, customer, create_user, make_reservation, booking_payload, released
    ):
        make_reservation(create_user(email="owner@example.com"), status=released)

        response = as_user(customer).post(URL, booking_payload(), format="json")

        assert response.status_code == 201

    def test_a_lapsed_request_no_longer_blocks_and_is_expired(
        self, as_user, customer, create_user, make_reservation, booking_payload
    ):
        owner = create_user(email="owner@example.com")
        lapsed = make_reservation(
            owner, status=ReservationStatus.PENDING, expires_at=timezone.now() - LAPSED_BY
        )

        response = as_user(customer).post(URL, booking_payload(), format="json")

        assert response.status_code == 201
        lapsed.refresh_from_db()
        assert lapsed.status == ReservationStatus.EXPIRED
        assert Notification.objects.filter(user=owner).count() == 1


class TestExpiry:
    def test_command_expires_lapsed_requests(self, customer, make_reservation):
        lapsed = make_reservation(
            customer, status=ReservationStatus.PENDING, expires_at=timezone.now() - LAPSED_BY
        )
        output = StringIO()

        call_command("expire_reservations", stdout=output)

        lapsed.refresh_from_db()
        assert lapsed.status == ReservationStatus.EXPIRED
        assert "Expired 1" in output.getvalue()

    def test_fresh_requests_are_left_alone(self, customer, make_reservation):
        fresh = make_reservation(
            customer,
            status=ReservationStatus.PENDING,
            expires_at=timezone.now() + timedelta(minutes=30),
        )
        output = StringIO()

        call_command("expire_reservations", stdout=output)

        fresh.refresh_from_db()
        assert fresh.status == ReservationStatus.PENDING
        assert "Expired 0" in output.getvalue()