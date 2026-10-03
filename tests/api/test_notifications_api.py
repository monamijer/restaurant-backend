import pytest

from apps.notifications.models import Notification, NotificationType

NOTIFICATIONS_URL = "/api/notifications/"

pytestmark = pytest.mark.django_db


def notify(user, message="Hello", is_read=False):
    return Notification.objects.create(
        user=user, type=NotificationType.SYSTEM, message=message, is_read=is_read
    )


def test_authentication_is_required(api_client):
    response = api_client.get(NOTIFICATIONS_URL)

    assert response.status_code == 401


def test_users_only_see_their_own_notifications(as_user, customer, staff_user):
    notify(customer, "Mine 1")
    notify(customer, "Mine 2")
    notify(staff_user, "Not mine")

    response = as_user(customer).get(NOTIFICATIONS_URL)

    assert response.data["count"] == 2
    assert {item["message"] for item in response.data["results"]} == {"Mine 1", "Mine 2"}


def test_unread_count(as_user, customer):
    notify(customer)
    notify(customer)
    notify(customer, is_read=True)

    response = as_user(customer).get(f"{NOTIFICATIONS_URL}unread-count/")

    assert response.status_code == 200
    assert response.data == {"unread": 2}


def test_mark_one_notification_as_read(as_user, customer):
    notification = notify(customer)

    response = as_user(customer).post(f"{NOTIFICATIONS_URL}{notification.pk}/mark-read/")

    assert response.status_code == 200
    notification.refresh_from_db()
    assert notification.is_read is True


def test_another_users_notification_is_not_found(as_user, customer, staff_user):
    foreign = notify(staff_user)

    response = as_user(customer).post(f"{NOTIFICATIONS_URL}{foreign.pk}/mark-read/")

    assert response.status_code == 404
    foreign.refresh_from_db()
    assert foreign.is_read is False


def test_mark_all_read_only_touches_the_requesting_user(as_user, customer, staff_user):
    notify(customer)
    notify(customer)
    others = notify(staff_user)

    response = as_user(customer).post(f"{NOTIFICATIONS_URL}mark-all-read/")

    assert response.data == {"updated": 2}
    others.refresh_from_db()
    assert others.is_read is False


def test_filter_unread_only(as_user, customer):
    notify(customer, "Unread")
    notify(customer, "Read", is_read=True)

    response = as_user(customer).get(NOTIFICATIONS_URL, {"is_read": "false"})

    assert [item["message"] for item in response.data["results"]] == ["Unread"]