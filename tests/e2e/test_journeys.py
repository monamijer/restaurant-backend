from datetime import timedelta

import pytest
from django.utils import timezone

from apps.tables.models import Table, TableStatus

from apps.tables.qr import make_token

pytestmark = pytest.mark.django_db

CUSTOMER_EMAIL = "new.customer@example.com"


def register_and_login(api_client, login, password, email=CUSTOMER_EMAIL):
    response = api_client.post(
        "/api/auth/register/",
        {"email": email, "password": password, "first_name": "Nadia", "last_name": "Ruzima"},
        format="json",
    )
    assert response.status_code == 201
    return login(email, password)


def body(response):
    return b"".join(response.streaming_content)


def test_a_new_customer_orders_pays_and_receives_an_invoice(
    api_client, login, password, staff_client, restaurant_floor
):
    dish, table = restaurant_floor["dish"], restaurant_floor["table"]
    customer = register_and_login(api_client, login, password)

    # The menu is public.
    menu = api_client.get("/api/menu-items/")
    assert [item["name"] for item in menu.data["results"]] == ["Grilled fish"]

    # Ordering on site opens the table.
    order = customer.post(
        "/api/orders/",
        {"order_type": "dine_in", "table": table.pk, "items": [{"menu_item": dish.pk, "quantity": 2}]},
        format="json",
    )
    assert order.status_code == 201
    assert order.data["total"] == "25.00"
    assert Table.objects.get(pk=table.pk).status == TableStatus.OCCUPIED

    # Paying by card settles the order and issues the invoice.
    payment = customer.post(
        "/api/payments/",
        {"order": order.data["id"], "method": "card", "payment_token": "tok_visa"},
        format="json",
    )
    assert payment.status_code == 201
    assert payment.data["status"] == "paid"

    # Staff run the order through the kitchen; the last step frees the table for cleaning.
    for new_status in ["confirmed", "preparing", "ready", "completed"]:
        step = staff_client.post(
            f"/api/orders/{order.data['id']}/update-status/", {"status": new_status}, format="json"
        )
        assert step.status_code == 200
    assert staff_client.get(f"/api/tables/{table.pk}/").data["status"] == "cleaning"

    # The customer finds the invoice and downloads a real PDF.
    invoices = customer.get("/api/invoices/")
    assert invoices.data["count"] == 1
    download = customer.get(f"/api/invoices/{invoices.data['results'][0]['id']}/download-pdf/")
    assert download.status_code == 200
    assert body(download).startswith(b"%PDF")

    # They were kept informed, and can clear their notifications.
    assert customer.get("/api/notifications/unread-count/").data["unread"] >= 3
    customer.post("/api/notifications/mark-all-read/")
    assert customer.get("/api/notifications/unread-count/").data["unread"] == 0


def test_a_customer_books_a_table_and_staff_decide(
    api_client, login, password, staff_client, restaurant_floor
):
    table = restaurant_floor["table"]
    customer = register_and_login(api_client, login, password)
    day = (timezone.now() + timedelta(days=7)).date().isoformat()
    query = {"date": day, "party_size": 2, "duration_minutes": 90}

    # Availability offers the evening slot.
    slots = customer.get("/api/reservations/availability/", query)
    assert "19:00" in [slot["time"] for slot in slots.data["slots"]]

    # The request holds the slot while it waits for staff.
    booked = customer.post(
        "/api/reservations/",
        {"table_token": make_token(table), "date": day, "time": "19:00", "duration_minutes": 90, "party_size": 2},
        format="json",
    )
    assert booked.status_code == 201
    assert booked.data["status"] == "pending"
    other_slots = customer.get("/api/reservations/availability/", {**query, "party_size": 2})
    assert "19:00" in [slot["time"] for slot in other_slots.data["slots"]]  # second table is free

    # Staff see it, confirm it, and the customer is told.
    pending = staff_client.get("/api/reservations/", {"status": "pending"})
    assert [item["id"] for item in pending.data["results"]] == [booked.data["id"]]
    confirmed = staff_client.post(f"/api/reservations/{booked.data['id']}/confirm/")
    assert confirmed.data["status"] == "confirmed"
    messages = [n["message"] for n in customer.get("/api/notifications/").data["results"]]
    assert any("confirmed" in message for message in messages)

    # Cancelling releases the slot and warns the staff.
    cancelled = customer.post(f"/api/reservations/{booked.data['id']}/cancel/")
    assert cancelled.data["status"] == "cancelled"
    staff_messages = [n["message"] for n in staff_client.get("/api/notifications/").data["results"]]
    assert any("cancelled" in message for message in staff_messages)


def test_a_party_joins_the_queue_and_is_called(
    api_client, login, password, staff_client, create_user, restaurant_floor
):
    assert api_client.get("/api/queue/summary/").data["waiting"] == 0
    first = register_and_login(api_client, login, password)
    second = register_and_login(api_client, login, password, email="second.guest@example.com")

    first_ticket = first.post("/api/queue/", {"party_size": 2}, format="json")
    second_ticket = second.post("/api/queue/", {"party_size": 4}, format="json")
    assert first_ticket.data["position"] == 1
    assert second_ticket.data["position"] == 2

    called = staff_client.post("/api/queue/call-next/")
    assert called.data["id"] == first_ticket.data["id"]
    assert called.data["status"] == "called"

    # The customer is told, and the second party moves up.
    messages = [n["message"] for n in first.get("/api/notifications/").data["results"]]
    assert any("almost ready" in message for message in messages)
    assert second.get("/api/queue/").data["results"][0]["position"] == 1

    seated = staff_client.post(f"/api/queue/{first_ticket.data['id']}/seat/")
    assert seated.data["status"] == "seated"