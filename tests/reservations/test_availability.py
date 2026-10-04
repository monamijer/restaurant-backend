import pytest

from apps.tables.models import Table

URL = "/api/reservations/availability/"

pytestmark = pytest.mark.django_db


def params(booking_day, **overrides):
    values = {"date": booking_day.isoformat(), "party_size": 2, "duration_minutes": 90}
    values.update(overrides)
    return values


def test_authentication_is_required(api_client, booking_day):
    assert api_client.get(URL, params(booking_day)).status_code == 401


def test_booked_slots_are_excluded_and_edges_respect_opening_hours(
    as_user, customer, create_user, make_reservation, booking_day
):
    make_reservation(create_user(email="owner@example.com"))  # 19:00 to 20:30

    response = as_user(customer).get(URL, params(booking_day))

    times = [slot["time"] for slot in response.data["slots"]]
    assert response.status_code == 200
    assert "17:30" in times and "20:30" in times
    assert not {"18:00", "19:00", "20:00"} & set(times)
    assert "21:00" not in times  # would end after the 22:00 closing time


def test_party_size_restricts_the_tables_offered(as_user, customer, table, booking_day):
    Table.objects.create(number=2, capacity=2)

    small_party = as_user(customer).get(URL, params(booking_day, party_size=2))
    large_party = as_user(customer).get(URL, params(booking_day, party_size=4))

    assert [t["number"] for t in small_party.data["slots"][0]["tables"]] == [1, 2]
    assert all(
        [t["number"] for t in slot["tables"]] == [1] for slot in large_party.data["slots"]
    )


def test_an_invalid_duration_is_rejected(as_user, customer, booking_day):
    response = as_user(customer).get(URL, params(booking_day, duration_minutes=45))

    assert response.status_code == 400
    assert "duration_minutes" in response.data["errors"]


def test_missing_parameters_are_rejected(as_user, customer):
    response = as_user(customer).get(URL)

    assert response.status_code == 400
    assert {"date", "party_size", "duration_minutes"} <= set(response.data["errors"])