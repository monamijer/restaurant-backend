import pytest
from rest_framework.test import APIClient

from apps.accounts import services
from apps.accounts.models import Role, User
from apps.core.api import ConflictError
from apps.orders.models import OrderStatus
from tests.concurrency_helpers import run_concurrently

URL = "/api/users/"

pytestmark = pytest.mark.django_db


def new_account(**overrides):
    payload = {
        "email": "new.waiter@example.com",
        "password": "S3cure-Passw0rd!",
        "first_name": "Nina",
        "last_name": "Waiter",
        "role": "staff",
    }
    payload.update(overrides)
    return payload


def real_client(email, password):
    """A client carrying a genuine JWT, to prove changes apply to sessions already open."""
    client = APIClient()
    tokens = client.post("/api/auth/login/", {"email": email, "password": password}, format="json").data
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    return client, tokens


class TestReadingAccounts:
    def test_staff_only_see_customers(self, as_user, staff_user, customer, admin_user):
        response = as_user(staff_user).get(URL)

        assert {item["role"] for item in response.data["results"]} == {"client"}
        assert [item["email"] for item in response.data["results"]] == [customer.email]

    def test_admins_see_every_account_and_can_filter(self, as_user, admin_user, staff_user, customer):
        everyone = as_user(admin_user).get(URL)
        only_staff = as_user(admin_user).get(URL, {"role": "staff"})
        searched = as_user(admin_user).get(URL, {"search": "customer@"})

        assert everyone.data["count"] == 3
        assert [item["email"] for item in only_staff.data["results"]] == [staff_user.email]
        assert [item["email"] for item in searched.data["results"]] == [customer.email]

    def test_customer_statistics_are_computed(self, as_user, staff_user, customer, make_order):
        make_order(customer, status=OrderStatus.COMPLETED, paid=True)
        make_order(customer, status=OrderStatus.CANCELLED)
        pending = make_order(customer)

        row = as_user(staff_user).get(f"{URL}{customer.pk}/").data

        assert row["orders_count"] == 2  # The cancelled order does not count.
        assert row["total_spent"] == "10.00"
        assert row["last_order_at"] is not None
        assert pending.pk

    def test_a_customer_without_orders_has_zero_statistics(self, as_user, staff_user, customer):
        row = as_user(staff_user).get(f"{URL}{customer.pk}/").data

        assert row["orders_count"] == 0
        assert row["total_spent"] == "0.00"
        assert row["last_order_at"] is None

    def test_customers_cannot_list_accounts(self, as_user, customer):
        assert as_user(customer).get(URL).status_code == 403

    def test_anonymous_cannot_list_accounts(self, api_client):
        assert api_client.get(URL).status_code == 401

    def test_staff_cannot_open_a_staff_or_admin_account(self, as_user, staff_user, admin_user):
        assert as_user(staff_user).get(f"{URL}{admin_user.pk}/").status_code == 404


class TestCreatingAccounts:
    def test_an_admin_creates_a_staff_account_that_can_sign_in(
        self, as_user, admin_user, api_client
    ):
        response = as_user(admin_user).post(URL, new_account(), format="json")

        assert response.status_code == 201
        assert response.data["role"] == "staff"
        assert "password" not in response.data
        login = APIClient().post(
            "/api/auth/login/",
            {"email": "new.waiter@example.com", "password": "S3cure-Passw0rd!"},
            format="json",
        )
        assert login.status_code == 200

    def test_staff_cannot_create_accounts(self, as_user, staff_user):
        assert as_user(staff_user).post(URL, new_account(), format="json").status_code == 403

    def test_a_weak_password_is_rejected(self, as_user, admin_user):
        response = as_user(admin_user).post(URL, new_account(password="12345678"), format="json")

        assert response.status_code == 400
        assert "password" in response.data["errors"]

    def test_a_duplicate_email_is_rejected_whatever_its_case(self, as_user, admin_user, customer):
        response = as_user(admin_user).post(
            URL, new_account(email=customer.email.upper()), format="json"
        )

        assert response.status_code == 400
        assert "email" in response.data["errors"]

    def test_an_unknown_role_is_rejected(self, as_user, admin_user):
        response = as_user(admin_user).post(URL, new_account(role="owner"), format="json")

        assert response.status_code == 400
        assert "role" in response.data["errors"]


class TestUpdatingAccounts:
    def test_a_role_change_applies_to_a_session_that_is_already_open(
        self, as_user, admin_user, create_user, password
    ):
        target = create_user(email="promoted@example.com")
        client, _ = real_client("promoted@example.com", password)
        assert client.get(URL).status_code == 403

        response = as_user(admin_user).patch(f"{URL}{target.pk}/", {"role": "staff"}, format="json")

        assert response.status_code == 200
        assert response.data["role"] == "staff"
        assert client.get(URL).status_code == 200

    def test_profile_fields_can_be_edited_but_not_the_email(self, as_user, admin_user, customer):
        response = as_user(admin_user).patch(
            f"{URL}{customer.pk}/",
            {"first_name": "Renamed", "email": "hijack@example.com"},
            format="json",
        )

        assert response.status_code == 200
        assert response.data["first_name"] == "Renamed"
        assert response.data["email"] == customer.email

    def test_an_admin_cannot_demote_themselves(self, as_user, admin_user):
        response = as_user(admin_user).patch(f"{URL}{admin_user.pk}/", {"role": "staff"}, format="json")

        assert response.status_code == 409

    def test_an_admin_cannot_deactivate_themselves(self, as_user, admin_user):
        response = as_user(admin_user).patch(
            f"{URL}{admin_user.pk}/", {"is_active": False}, format="json"
        )

        assert response.status_code == 409

    def test_a_deactivated_user_is_locked_out_immediately(
        self, as_user, admin_user, create_user, password
    ):
        victim = create_user(email="victim@example.com")
        client, tokens = real_client("victim@example.com", password)
        assert client.get("/api/auth/me/").status_code == 200

        response = as_user(admin_user).patch(f"{URL}{victim.pk}/", {"is_active": False}, format="json")

        assert response.status_code == 200
        assert client.get("/api/auth/me/").status_code == 401
        refresh = APIClient().post("/api/auth/refresh/", {"refresh": tokens["refresh"]}, format="json")
        login = APIClient().post(
            "/api/auth/login/", {"email": "victim@example.com", "password": password}, format="json"
        )
        assert refresh.status_code == 401
        assert login.status_code == 401

    def test_staff_cannot_edit_accounts(self, as_user, staff_user, customer):
        response = as_user(staff_user).patch(f"{URL}{customer.pk}/", {"first_name": "X"}, format="json")

        assert response.status_code == 403

    def test_put_and_delete_do_not_exist(self, as_user, admin_user, customer):
        client = as_user(admin_user)

        assert client.put(f"{URL}{customer.pk}/", {}, format="json").status_code == 405
        assert client.delete(f"{URL}{customer.pk}/").status_code == 405


class TestAdministratorPasswordReset:
    def test_an_admin_sets_a_new_password(self, as_user, admin_user, create_user, password):
        target = create_user(email="forgetful@example.com")

        response = as_user(admin_user).post(
            f"{URL}{target.pk}/set-password/", {"password": "An0ther-Strong-Pass!"}, format="json"
        )

        old = APIClient().post(
            "/api/auth/login/", {"email": target.email, "password": password}, format="json"
        )
        new = APIClient().post(
            "/api/auth/login/",
            {"email": target.email, "password": "An0ther-Strong-Pass!"},
            format="json",
        )
        assert response.status_code == 204
        assert old.status_code == 401
        assert new.status_code == 200

    def test_a_weak_replacement_is_rejected(self, as_user, admin_user, customer):
        response = as_user(admin_user).post(
            f"{URL}{customer.pk}/set-password/", {"password": "12345678"}, format="json"
        )

        assert response.status_code == 400

    def test_staff_cannot_reset_passwords(self, as_user, staff_user, customer):
        response = as_user(staff_user).post(
            f"{URL}{customer.pk}/set-password/", {"password": "An0ther-Strong-Pass!"}, format="json"
        )

        assert response.status_code == 403


@pytest.mark.django_db(transaction=True)
def test_two_admins_cannot_demote_each_other_at_once(create_user):
    first = create_user(email="first.admin@example.com", role=Role.ADMIN)
    second = create_user(email="second.admin@example.com", role=Role.ADMIN)

    outcomes = run_concurrently(
        [
            lambda: services.update_user(second.pk, actor=first, changes={"role": Role.STAFF}),
            lambda: services.update_user(first.pk, actor=second, changes={"role": Role.STAFF}),
        ]
    )

    assert sorted(outcomes) == ["conflict", "ok"]
    assert User.objects.filter(role=Role.ADMIN, is_active=True).count() == 1