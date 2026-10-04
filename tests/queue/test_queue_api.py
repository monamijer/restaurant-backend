import pytest

from apps.core.models import RestaurantSettings
from apps.notifications.models import Notification
from apps.queue_mgmt.models import QueueStatus, QueueTicket

URL = "/api/queue/"
DEFAULT_MINUTES_PER_PARTY = 10

pytestmark = pytest.mark.django_db


def make_ticket(**overrides):
    values = {"customer_name": "Walk-in", "party_size": 2}
    values.update(overrides)
    return QueueTicket.objects.create(**values)


def positions_by_id(response):
    return {item["id"]: item["position"] for item in response.data["results"]}


class TestJoining:
    def test_a_customer_joins_under_their_own_name(self, as_user, customer):
        response = as_user(customer).post(URL, {"party_size": 2}, format="json")

        assert response.status_code == 201
        assert response.data["customer"] == customer.pk
        assert response.data["customer_name"] == "Test Customer"
        assert response.data["status"] == "waiting"
        assert response.data["position"] == 1
        assert response.data["estimated_wait_minutes"] == 0

    def test_later_arrivals_queue_behind_with_a_longer_wait(
        self, as_user, customer, create_user
    ):
        as_user(customer).post(URL, {"party_size": 2}, format="json")

        response = as_user(create_user(email="second@example.com")).post(
            URL, {"party_size": 3}, format="json"
        )

        assert response.data["position"] == 2
        assert response.data["estimated_wait_minutes"] == DEFAULT_MINUTES_PER_PARTY
        assert response.data["quoted_wait_minutes"] == DEFAULT_MINUTES_PER_PARTY

    def test_anonymous_cannot_join(self, api_client):
        response = api_client.post(URL, {"party_size": 2}, format="json")

        assert response.status_code == 401

    def test_an_account_cannot_hold_two_active_tickets(self, as_user, customer):
        as_user(customer).post(URL, {"party_size": 2}, format="json")

        response = as_user(customer).post(URL, {"party_size": 2}, format="json")

        assert response.status_code == 409
        assert response.data["code"] == "CONFLICT"

    def test_a_customer_can_rejoin_after_cancelling(self, as_user, customer):
        first = as_user(customer).post(URL, {"party_size": 2}, format="json")
        as_user(customer).post(f"{URL}{first.data['id']}/cancel/")

        response = as_user(customer).post(URL, {"party_size": 2}, format="json")

        assert response.status_code == 201

    def test_staff_register_a_walk_in_guest(self, as_user, staff_user):
        payload = {"customer_name": "Walk-in Guest", "phone": "+25712345678", "party_size": 3}

        response = as_user(staff_user).post(URL, payload, format="json")

        assert response.status_code == 201
        assert response.data["customer"] is None
        assert response.data["customer_name"] == "Walk-in Guest"

    def test_staff_must_name_a_walk_in_guest(self, as_user, staff_user):
        response = as_user(staff_user).post(URL, {"party_size": 3}, format="json")

        assert response.status_code == 400
        assert "customer_name" in response.data["errors"]

    def test_walk_in_guests_are_not_limited_to_one_ticket(self, as_user, staff_user):
        payload = {"customer_name": "Walk-in Guest", "party_size": 2}

        first = as_user(staff_user).post(URL, payload, format="json")
        second = as_user(staff_user).post(URL, payload, format="json")

        assert first.status_code == second.status_code == 201

    @pytest.mark.parametrize("party_size", [0, 21])
    def test_party_size_is_bounded(self, as_user, customer, party_size):
        response = as_user(customer).post(URL, {"party_size": party_size}, format="json")

        assert response.status_code == 400
        assert "party_size" in response.data["errors"]

    def test_an_invalid_phone_is_rejected(self, as_user, customer):
        response = as_user(customer).post(
            URL, {"party_size": 2, "phone": "not-a-phone"}, format="json"
        )

        assert response.status_code == 400
        assert "phone" in response.data["errors"]


class TestVisibility:
    def test_customers_only_see_their_own_tickets(self, as_user, customer, create_user):
        make_ticket(customer=customer, customer_name="Mine")
        make_ticket(customer=create_user(email="other@example.com"), customer_name="Other")

        response = as_user(customer).get(URL)

        assert [item["customer_name"] for item in response.data["results"]] == ["Mine"]

    def test_staff_see_every_ticket_with_consecutive_positions(self, as_user, staff_user):
        tickets = [make_ticket(customer_name=f"Guest {n}") for n in range(3)]

        response = as_user(staff_user).get(URL)

        assert positions_by_id(response) == {
            tickets[0].pk: 1,
            tickets[1].pk: 2,
            tickets[2].pk: 3,
        }

    def test_a_foreign_ticket_is_not_found(self, as_user, customer, create_user):
        foreign = make_ticket(customer=create_user(email="other@example.com"))

        response = as_user(customer).get(f"{URL}{foreign.pk}/")

        assert response.status_code == 404

    def test_filter_active_keeps_waiting_and_called_tickets(self, as_user, staff_user):
        make_ticket(customer_name="Waiting")
        make_ticket(customer_name="Called", status=QueueStatus.CALLED)
        make_ticket(customer_name="Seated", status=QueueStatus.SEATED)

        response = as_user(staff_user).get(URL, {"active": "true"})

        names = {item["customer_name"] for item in response.data["results"]}
        assert names == {"Waiting", "Called"}


class TestCalling:
    def test_call_next_calls_the_oldest_waiting_ticket(self, as_user, staff_user):
        oldest = make_ticket(customer_name="First")
        newest = make_ticket(customer_name="Second")

        response = as_user(staff_user).post(f"{URL}call-next/")

        assert response.status_code == 200
        assert response.data["id"] == oldest.pk
        assert response.data["status"] == "called"
        assert response.data["called_at"] is not None
        assert response.data["position"] is None
        listing = as_user(staff_user).get(URL, {"status": "waiting"})
        assert positions_by_id(listing) == {newest.pk: 1}

    def test_a_called_customer_is_notified_but_a_walk_in_is_not_a_problem(
        self, as_user, staff_user, customer
    ):
        make_ticket(customer=customer)
        make_ticket(customer_name="Walk-in")

        as_user(staff_user).post(f"{URL}call-next/")
        as_user(staff_user).post(f"{URL}call-next/")

        assert Notification.objects.filter(user=customer, type="queue").count() == 1

    def test_call_next_on_an_empty_queue_is_a_conflict(self, as_user, staff_user):
        response = as_user(staff_user).post(f"{URL}call-next/")

        assert response.status_code == 409
        assert response.data["code"] == "CONFLICT"

    def test_staff_can_call_a_specific_ticket_out_of_order(self, as_user, staff_user):
        first = make_ticket(customer_name="First")
        second = make_ticket(customer_name="Second")

        response = as_user(staff_user).post(f"{URL}{second.pk}/call/")

        assert response.status_code == 200
        assert response.data["status"] == "called"
        listing = as_user(staff_user).get(URL, {"status": "waiting"})
        assert positions_by_id(listing) == {first.pk: 1}

    def test_a_ticket_cannot_be_called_twice(self, as_user, staff_user):
        ticket = make_ticket()
        as_user(staff_user).post(f"{URL}{ticket.pk}/call/")

        response = as_user(staff_user).post(f"{URL}{ticket.pk}/call/")

        assert response.status_code == 409

    def test_customers_cannot_call(self, as_user, customer):
        ticket = make_ticket(customer=customer)

        assert as_user(customer).post(f"{URL}{ticket.pk}/call/").status_code == 403
        assert as_user(customer).post(f"{URL}call-next/").status_code == 403


class TestCompletion:
    def test_staff_seat_a_called_ticket(self, as_user, staff_user):
        ticket = make_ticket(status=QueueStatus.CALLED)

        response = as_user(staff_user).post(f"{URL}{ticket.pk}/seat/")

        assert response.status_code == 200
        assert response.data["status"] == "seated"
        assert response.data["completed_at"] is not None

    def test_a_waiting_ticket_cannot_be_seated(self, as_user, staff_user):
        ticket = make_ticket()

        response = as_user(staff_user).post(f"{URL}{ticket.pk}/seat/")

        assert response.status_code == 409

    def test_no_show_only_follows_a_call(self, as_user, staff_user):
        called = make_ticket(status=QueueStatus.CALLED)
        waiting = make_ticket()

        ok = as_user(staff_user).post(f"{URL}{called.pk}/no-show/")
        refused = as_user(staff_user).post(f"{URL}{waiting.pk}/no-show/")

        assert ok.status_code == 200
        assert ok.data["status"] == "no_show"
        assert refused.status_code == 409

    def test_customers_cannot_seat(self, as_user, customer):
        ticket = make_ticket(customer=customer, status=QueueStatus.CALLED)

        response = as_user(customer).post(f"{URL}{ticket.pk}/seat/")

        assert response.status_code == 403


class TestCancellation:
    def test_cancelling_moves_everyone_behind_forward(
        self, as_user, customer, create_user
    ):
        mine = make_ticket(customer=customer)
        behind_owner = create_user(email="behind@example.com")
        behind = make_ticket(customer=behind_owner)

        response = as_user(customer).post(f"{URL}{mine.pk}/cancel/")
        listing = as_user(behind_owner).get(URL)

        assert response.status_code == 200
        assert response.data["status"] == "cancelled"
        assert response.data["completed_at"] is not None
        assert positions_by_id(listing) == {behind.pk: 1}

    def test_a_customer_can_cancel_after_being_called(self, as_user, customer):
        ticket = make_ticket(customer=customer, status=QueueStatus.CALLED)

        response = as_user(customer).post(f"{URL}{ticket.pk}/cancel/")

        assert response.status_code == 200

    def test_a_customer_cannot_cancel_someone_elses_ticket(
        self, as_user, customer, create_user
    ):
        foreign = make_ticket(customer=create_user(email="other@example.com"))

        response = as_user(customer).post(f"{URL}{foreign.pk}/cancel/")

        assert response.status_code == 404

    def test_staff_cancel_and_the_customer_is_told(self, as_user, staff_user, customer):
        ticket = make_ticket(customer=customer)

        response = as_user(staff_user).post(f"{URL}{ticket.pk}/cancel/")

        assert response.status_code == 200
        assert Notification.objects.filter(
            user=customer, message__contains="removed"
        ).exists()

    def test_cancelling_twice_is_a_conflict(self, as_user, customer):
        ticket = make_ticket(customer=customer)
        as_user(customer).post(f"{URL}{ticket.pk}/cancel/")

        response = as_user(customer).post(f"{URL}{ticket.pk}/cancel/")

        assert response.status_code == 409


class TestSummary:
    def test_the_summary_is_public(self, api_client):
        for number in range(3):
            make_ticket(customer_name=f"Guest {number}")

        response = api_client.get(f"{URL}summary/")

        assert response.status_code == 200
        assert response.data == {
            "waiting": 3,
            "estimated_wait_minutes": 3 * DEFAULT_MINUTES_PER_PARTY,
        }

    def test_the_summary_follows_the_configured_minutes(self, api_client):
        restaurant = RestaurantSettings.load()
        restaurant.queue_minutes_per_party = 5
        restaurant.save()
        for number in range(3):
            make_ticket(customer_name=f"Guest {number}")

        response = api_client.get(f"{URL}summary/")

        assert response.data["estimated_wait_minutes"] == 15