from datetime import timedelta

import pytest
from django.utils import timezone

from apps.notifications.models import Notification
from apps.reservations.models import ReservationStatus

URL = "/api/reservations/"
HOLD = timedelta(minutes=30)

pytestmark = pytest.mark.django_db


@pytest.fixture
def pending_reservation(customer, make_reservation):
    return make_reservation(
        customer, status=ReservationStatus.PENDING, expires_at=timezone.now() + HOLD
    )


class TestVisibility:
    def test_anonymous_cannot_list(self, api_client):
        assert api_client.get(URL).status_code == 401

    def test_customers_only_see_their_own_reservations(
        self, as_user, customer, create_user, make_reservation, table
    ):
        make_reservation(customer)
        make_reservation(create_user(email="other@example.com"), hour=12)

        response = as_user(customer).get(URL)

        assert response.data["count"] == 1
        assert response.data["results"][0]["customer"] == customer.pk

    def test_staff_see_every_reservation(
        self, as_user, staff_user, customer, create_user, make_reservation
    ):
        make_reservation(customer)
        make_reservation(create_user(email="other@example.com"), hour=12)

        response = as_user(staff_user).get(URL)

        assert response.data["count"] == 2

    def test_a_foreign_reservation_is_not_found(
        self, as_user, customer, create_user, make_reservation
    ):
        foreign = make_reservation(create_user(email="other@example.com"))

        response = as_user(customer).get(f"{URL}{foreign.pk}/")

        assert response.status_code == 404


class TestConfirmation:
    def test_staff_confirms_and_the_customer_is_notified(
        self, as_user, staff_user, customer, pending_reservation
    ):
        response = as_user(staff_user).post(f"{URL}{pending_reservation.pk}/confirm/")

        assert response.status_code == 200
        assert response.data["status"] == "confirmed"
        assert response.data["expires_at"] is None
        assert Notification.objects.filter(user=customer, message__contains="confirmed").exists()

    def test_customers_cannot_confirm(self, as_user, customer, pending_reservation):
        response = as_user(customer).post(f"{URL}{pending_reservation.pk}/confirm/")

        assert response.status_code == 403

    def test_confirming_twice_is_a_conflict(self, as_user, staff_user, pending_reservation):
        as_user(staff_user).post(f"{URL}{pending_reservation.pk}/confirm/")

        response = as_user(staff_user).post(f"{URL}{pending_reservation.pk}/confirm/")

        assert response.status_code == 409

    def test_a_lapsed_request_cannot_be_confirmed(
        self, as_user, staff_user, customer, make_reservation
    ):
        lapsed = make_reservation(
            customer,
            status=ReservationStatus.PENDING,
            expires_at=timezone.now() - timedelta(minutes=1),
        )

        response = as_user(staff_user).post(f"{URL}{lapsed.pk}/confirm/")

        assert response.status_code == 409
        assert response.data["code"] == "CONFLICT"

    def test_staff_rejects_and_the_customer_is_notified(
        self, as_user, staff_user, customer, pending_reservation
    ):
        response = as_user(staff_user).post(f"{URL}{pending_reservation.pk}/reject/")

        assert response.status_code == 200
        assert response.data["status"] == "rejected"
        assert Notification.objects.filter(
            user=customer, message__contains="could not be accepted"
        ).exists()

    def test_a_confirmed_reservation_cannot_be_rejected(
        self, as_user, staff_user, customer, make_reservation
    ):
        confirmed = make_reservation(customer)

        response = as_user(staff_user).post(f"{URL}{confirmed.pk}/reject/")

        assert response.status_code == 409


class TestCancellation:
    def test_customer_cancels_their_own_and_staff_are_notified(
        self, as_user, customer, staff_user, pending_reservation
    ):
        response = as_user(customer).post(f"{URL}{pending_reservation.pk}/cancel/")

        assert response.status_code == 200
        assert response.data["status"] == "cancelled"
        assert Notification.objects.filter(user=staff_user, type="reservation").count() == 1

    def test_customer_cannot_cancel_someone_elses(
        self, as_user, customer, create_user, make_reservation
    ):
        foreign = make_reservation(create_user(email="other@example.com"))

        response = as_user(customer).post(f"{URL}{foreign.pk}/cancel/")

        assert response.status_code == 404

    def test_customer_cannot_cancel_after_the_start(
        self, as_user, customer, make_reservation, booking_day
    ):
        started = make_reservation(customer, day=booking_day - timedelta(days=30))

        response = as_user(customer).post(f"{URL}{started.pk}/cancel/")

        assert response.status_code == 409

    def test_staff_cancel_and_the_customer_is_notified(
        self, as_user, staff_user, customer, make_reservation
    ):
        confirmed = make_reservation(customer)

        response = as_user(staff_user).post(f"{URL}{confirmed.pk}/cancel/")

        assert response.status_code == 200
        assert Notification.objects.filter(
            user=customer, message__contains="cancelled by the restaurant"
        ).exists()

    def test_cancelling_twice_is_a_conflict(self, as_user, customer, pending_reservation):
        as_user(customer).post(f"{URL}{pending_reservation.pk}/cancel/")

        response = as_user(customer).post(f"{URL}{pending_reservation.pk}/cancel/")

        assert response.status_code == 409


class TestCompletion:
    def test_staff_complete_a_confirmed_reservation(
        self, as_user, staff_user, customer, make_reservation
    ):
        confirmed = make_reservation(customer)

        response = as_user(staff_user).post(f"{URL}{confirmed.pk}/complete/")

        assert response.status_code == 200
        assert response.data["status"] == "completed"

    def test_a_pending_reservation_cannot_be_completed(
        self, as_user, staff_user, pending_reservation
    ):
        response = as_user(staff_user).post(f"{URL}{pending_reservation.pk}/complete/")

        assert response.status_code == 409

    def test_staff_can_record_a_no_show(self, as_user, staff_user, customer, make_reservation):
        confirmed = make_reservation(customer)

        response = as_user(staff_user).post(f"{URL}{confirmed.pk}/no-show/")

        assert response.status_code == 200
        assert response.data["status"] == "no_show"

    def test_customers_cannot_complete(self, as_user, customer, make_reservation):
        confirmed = make_reservation(customer)

        response = as_user(customer).post(f"{URL}{confirmed.pk}/complete/")

        assert response.status_code == 403


class TestFilters:
    def test_filter_by_status(self, as_user, staff_user, customer, make_reservation):
        make_reservation(customer, hour=12)
        make_reservation(
            customer,
            hour=15,
            status=ReservationStatus.PENDING,
            expires_at=timezone.now() + HOLD,
        )

        response = as_user(staff_user).get(URL, {"status": "pending"})

        assert response.data["count"] == 1
        assert response.data["results"][0]["status"] == "pending"

    def test_filter_by_local_day(
        self, as_user, staff_user, customer, make_reservation, booking_day
    ):
        make_reservation(customer, day=booking_day)
        make_reservation(customer, day=booking_day + timedelta(days=1))

        response = as_user(staff_user).get(URL, {"date": booking_day.isoformat()})

        assert response.data["count"] == 1
        assert response.data["results"][0]["date"] == booking_day.isoformat()