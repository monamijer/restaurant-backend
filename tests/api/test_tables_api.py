from datetime import timedelta

import pytest
from django.utils import timezone

from apps.reservations.models import Reservation
from apps.tables.models import Table, TableStatus

TABLES_URL = "/api/tables/"

pytestmark = pytest.mark.django_db


def make_table(number, capacity=4, **overrides):
    return Table.objects.create(number=number, capacity=capacity, **overrides)


def test_anonymous_cannot_list_tables(api_client):
    response = api_client.get(TABLES_URL)

    assert response.status_code == 401


def test_any_signed_in_user_can_list_tables(as_user, customer):
    make_table(1)

    response = as_user(customer).get(TABLES_URL)

    assert response.status_code == 200
    assert response.data["count"] == 1


@pytest.mark.parametrize("user_fixture", ["customer", "staff_user"])
def test_only_admins_can_create_tables(user_fixture, request, as_user):
    user = request.getfixturevalue(user_fixture)

    response = as_user(user).post(TABLES_URL, {"number": 1, "capacity": 4}, format="json")

    assert response.status_code == 403


def test_admin_creates_a_table_that_starts_available(as_user, admin_user):
    response = as_user(admin_user).post(
        TABLES_URL, {"number": 7, "capacity": 4, "location": "Terrace"}, format="json"
    )

    assert response.status_code == 201
    assert response.data["status"] == TableStatus.AVAILABLE


def test_duplicate_table_number_is_rejected(as_user, admin_user):
    make_table(3)

    response = as_user(admin_user).post(TABLES_URL, {"number": 3, "capacity": 2}, format="json")

    assert response.status_code == 400
    assert "number" in response.data["errors"]


def test_zero_capacity_is_rejected(as_user, admin_user):
    response = as_user(admin_user).post(TABLES_URL, {"number": 4, "capacity": 0}, format="json")

    assert response.status_code == 400
    assert "capacity" in response.data["errors"]


def test_status_cannot_be_changed_through_crud(as_user, admin_user):
    table = make_table(1)

    response = as_user(admin_user).patch(
        f"{TABLES_URL}{table.pk}/", {"status": TableStatus.OCCUPIED}, format="json"
    )

    assert response.status_code == 200
    table.refresh_from_db()
    assert table.status == TableStatus.AVAILABLE


def test_staff_can_set_the_status(as_user, staff_user):
    table = make_table(1)

    response = as_user(staff_user).post(
        f"{TABLES_URL}{table.pk}/set-status/", {"status": TableStatus.CLEANING}, format="json"
    )

    assert response.status_code == 200
    table.refresh_from_db()
    assert table.status == TableStatus.CLEANING


def test_unknown_status_is_rejected(as_user, staff_user):
    table = make_table(1)

    response = as_user(staff_user).post(
        f"{TABLES_URL}{table.pk}/set-status/", {"status": "exploded"}, format="json"
    )

    assert response.status_code == 400
    assert "status" in response.data["errors"]


def test_customers_cannot_set_the_status(as_user, customer):
    table = make_table(1)

    response = as_user(customer).post(
        f"{TABLES_URL}{table.pk}/set-status/", {"status": TableStatus.OCCUPIED}, format="json"
    )

    assert response.status_code == 403


def test_filter_by_status_and_minimum_capacity(as_user, staff_user):
    make_table(1, capacity=2)
    make_table(2, capacity=6)
    make_table(3, capacity=6, status=TableStatus.OCCUPIED)

    response = as_user(staff_user).get(TABLES_URL, {"status": "available", "min_capacity": 4})

    assert [table["number"] for table in response.data["results"]] == [2]


def test_table_with_a_reservation_cannot_be_deleted(as_user, admin_user, customer):
    table = make_table(1)
    starts_at = timezone.now() + timedelta(days=1)
    Reservation.objects.create(
        customer=customer,
        table=table,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=1),
        party_size=2,
    )

    response = as_user(admin_user).delete(f"{TABLES_URL}{table.pk}/")

    assert response.status_code == 409
    assert response.data["code"] == "CONFLICT"