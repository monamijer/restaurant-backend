import pytest
from rest_framework.test import APIClient

URL = "/api/auth/change-password/"
NEW_PASSWORD = "Brand-New-Passw0rd!"

pytestmark = pytest.mark.django_db


def login(email, password):
    return APIClient().post(
        "/api/auth/login/", {"email": email, "password": password}, format="json"
    )


def test_changing_the_password_switches_credentials_and_returns_fresh_tokens(
    as_user, customer, password
):
    response = as_user(customer).post(
        URL, {"old_password": password, "new_password": NEW_PASSWORD}, format="json"
    )

    assert response.status_code == 200
    assert response.data["access"] and response.data["refresh"]
    assert login(customer.email, password).status_code == 401
    assert login(customer.email, NEW_PASSWORD).status_code == 200


def test_the_wrong_current_password_is_refused(as_user, customer):
    response = as_user(customer).post(
        URL, {"old_password": "not-my-password", "new_password": NEW_PASSWORD}, format="json"
    )

    assert response.status_code == 400
    assert "old_password" in response.data["errors"]


def test_a_weak_new_password_is_refused(as_user, customer, password):
    response = as_user(customer).post(
        URL, {"old_password": password, "new_password": "12345678"}, format="json"
    )

    assert response.status_code == 400
    assert "new_password" in response.data["errors"]


def test_other_sessions_are_signed_out_but_the_new_one_works(as_user, customer, password):
    before = login(customer.email, password).data

    changed = as_user(customer).post(
        URL, {"old_password": password, "new_password": NEW_PASSWORD}, format="json"
    )

    old_refresh = APIClient().post("/api/auth/refresh/", {"refresh": before["refresh"]}, format="json")
    new_refresh = APIClient().post(
        "/api/auth/refresh/", {"refresh": changed.data["refresh"]}, format="json"
    )
    assert old_refresh.status_code == 401
    assert new_refresh.status_code == 200


def test_anonymous_cannot_change_a_password(api_client):
    response = api_client.post(URL, {"old_password": "a", "new_password": "b"}, format="json")

    assert response.status_code == 401