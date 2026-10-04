import pytest

SETTINGS_URL = "/api/settings/"

pytestmark = pytest.mark.django_db


def test_anyone_can_read_the_settings(api_client):
    response = api_client.get(SETTINGS_URL)

    assert response.status_code == 200
    assert response.data["timezone"] == "UTC"
    assert "opening_time" in response.data


@pytest.mark.parametrize("user_fixture", ["customer", "staff_user"])
def test_non_admins_cannot_update(user_fixture, request, as_user):
    user = request.getfixturevalue(user_fixture)

    response = as_user(user).patch(SETTINGS_URL, {"name": "Hacked"}, format="json")

    assert response.status_code == 403
    assert response.data["code"] == "PERMISSION_DENIED"


def test_anonymous_cannot_update(api_client):
    response = api_client.patch(SETTINGS_URL, {"name": "Hacked"}, format="json")

    assert response.status_code == 401


def test_admin_can_update(as_user, admin_user):
    response = as_user(admin_user).patch(
        SETTINGS_URL, {"name": "Chez Test", "timezone": "Europe/Paris"}, format="json"
    )

    assert response.status_code == 200
    assert response.data["name"] == "Chez Test"
    assert response.data["timezone"] == "Europe/Paris"


def test_unknown_timezone_is_rejected(as_user, admin_user):
    response = as_user(admin_user).patch(SETTINGS_URL, {"timezone": "Mars/Olympus"}, format="json")

    assert response.status_code == 400
    assert response.data["code"] == "VALIDATION_ERROR"
    assert "timezone" in response.data["errors"]


def test_closing_time_must_follow_opening_time(as_user, admin_user):
    response = as_user(admin_user).patch(SETTINGS_URL, {"opening_time": "23:00:00"}, format="json")

    assert response.status_code == 400
    assert "closing_time" in response.data["errors"]


def test_put_is_not_allowed(as_user, admin_user):
    response = as_user(admin_user).put(SETTINGS_URL, {"name": "Replaced"}, format="json")

    assert response.status_code == 405
    assert response.data["code"] == "METHOD_NOT_ALLOWED"

def test_queue_minutes_per_party_must_be_positive(as_user, admin_user):
    response = as_user(admin_user).patch(
        SETTINGS_URL, {"queue_minutes_per_party": 0}, format="json"
    )

    assert response.status_code == 400
    assert "queue_minutes_per_party" in response.data["errors"]