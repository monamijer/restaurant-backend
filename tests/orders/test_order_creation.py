from decimal import Decimal

import pytest

from apps.core.models import RestaurantSettings
from apps.menu.models import MenuItem
from apps.notifications.models import Notification
from apps.orders.models import Order
from apps.tables.models import TableStatus

from apps.tables.qr import make_token

URL = "/api/orders/"

pytestmark = pytest.mark.django_db


def set_tax_rate(rate):
    restaurant = RestaurantSettings.load()
    restaurant.tax_rate = Decimal(rate)
    restaurant.save()


class TestCreationAndTotals:
    def test_a_customer_creates_a_takeaway_order(
        self, as_user, customer, staff_user, order_payload
    ):
        response = as_user(customer).post(URL, order_payload(), format="json")

        assert response.status_code == 201
        assert response.data["status"] == "pending"
        assert response.data["customer"] == customer.pk
        assert response.data["subtotal"] == "25.00"
        assert response.data["tax_amount"] == "0.00"
        assert response.data["total"] == "25.00"
        assert response.data["currency"] == "USD"
        assert response.data["items"][0]["unit_price"] == "12.50"
        assert Notification.objects.filter(user=staff_user, type="order").count() == 1

    def test_totals_are_computed_by_the_server_and_client_amounts_are_ignored(
        self, as_user, customer, dish, side
    ):
        set_tax_rate("10.00")
        payload = {
            "order_type": "takeaway",
            "total": "0.01",
            "subtotal": "0.01",
            "items": [
                {"menu_item": dish.pk, "quantity": 2, "unit_price": "0.01"},
                {"menu_item": side.pk, "quantity": 1, "unit_price": "0.01"},
            ],
        }

        response = as_user(customer).post(URL, payload, format="json")

        # 2 x 12.50 + 1 x 6.00 = 31.00; 10% tax = 3.10
        assert response.status_code == 201
        assert response.data["subtotal"] == "31.00"
        assert response.data["tax_amount"] == "3.10"
        assert response.data["total"] == "34.10"

    def test_tax_is_rounded_half_up(self, as_user, customer, category):
        set_tax_rate("10.00")
        cheap = MenuItem.objects.create(category=category, name="Sweet", price=Decimal("1.05"))
        payload = {"order_type": "takeaway", "items": [{"menu_item": cheap.pk, "quantity": 1}]}

        response = as_user(customer).post(URL, payload, format="json")

        # 1.05 x 10% = 0.105, which rounds half up to 0.11
        assert response.data["tax_amount"] == "0.11"
        assert response.data["total"] == "1.16"

    def test_prices_and_names_are_frozen_at_order_time(
        self, as_user, customer, dish, order_payload
    ):
        created = as_user(customer).post(URL, order_payload(), format="json")
        dish.name = "Renamed"
        dish.price = Decimal("99.00")
        dish.save()

        response = as_user(customer).get(f"{URL}{created.data['id']}/")

        assert response.data["items"][0]["unit_price"] == "12.50"
        assert response.data["items"][0]["item_name"] == "Grilled fish"
        assert response.data["total"] == "25.00"

    def test_the_tax_rate_is_frozen_at_order_time(self, as_user, customer, order_payload):
        set_tax_rate("10.00")
        created = as_user(customer).post(URL, order_payload(), format="json")
        set_tax_rate("0.00")

        response = as_user(customer).get(f"{URL}{created.data['id']}/")

        assert response.data["tax_rate"] == "10.00"
        assert response.data["tax_amount"] == "2.50"

    def test_the_same_dish_on_two_lines_stays_two_lines(self, as_user, customer, dish):
        payload = {
            "order_type": "takeaway",
            "items": [
                {"menu_item": dish.pk, "quantity": 1, "special_instructions": "No salt"},
                {"menu_item": dish.pk, "quantity": 1, "special_instructions": "Extra lemon"},
            ],
        }

        response = as_user(customer).post(URL, payload, format="json")

        assert response.status_code == 201
        assert len(response.data["items"]) == 2
        assert response.data["subtotal"] == "25.00"

    def test_anonymous_cannot_order(self, api_client, order_payload):
        response = api_client.post(URL, order_payload(), format="json")

        assert response.status_code == 401


class TestDishValidation:
    def test_an_unavailable_dish_is_rejected_on_its_own_line(
        self, as_user, customer, dish, side
    ):
        side.is_available = False
        side.save()
        payload = {
            "order_type": "takeaway",
            "items": [
                {"menu_item": dish.pk, "quantity": 1},
                {"menu_item": side.pk, "quantity": 1},
            ],
        }

        response = as_user(customer).post(URL, payload, format="json")

        assert response.status_code == 400
        assert response.data["errors"]["items"][0] == {}
        assert "menu_item" in response.data["errors"]["items"][1]
        assert Order.objects.count() == 0

    def test_an_unknown_dish_is_rejected(self, as_user, customer):
        payload = {"order_type": "takeaway", "items": [{"menu_item": 9999, "quantity": 1}]}

        response = as_user(customer).post(URL, payload, format="json")

        assert response.status_code == 400
        assert "menu_item" in response.data["errors"]["items"][0]

    def test_an_order_needs_at_least_one_line(self, as_user, customer, order_payload):
        response = as_user(customer).post(URL, order_payload(items=[]), format="json")

        assert response.status_code == 400
        assert "items" in response.data["errors"]

    @pytest.mark.parametrize("quantity", [0, 51])
    def test_quantity_is_bounded(self, as_user, customer, dish, order_payload, quantity):
        items = [{"menu_item": dish.pk, "quantity": quantity}]

        response = as_user(customer).post(URL, order_payload(items=items), format="json")

        assert response.status_code == 400
        assert "quantity" in response.data["errors"]["items"][0]


class TestOrderTypeRules:
    def test_a_customer_dining_in_must_scan_a_table_code(self, as_user, customer, order_payload):
        response = as_user(customer).post(URL, order_payload(order_type="dine_in"), format="json")

        assert response.status_code == 400
        assert "table_token" in response.data["errors"]

    def test_staff_dining_in_must_name_a_table(self, as_user, staff_user, order_payload):
        response = as_user(staff_user).post(URL, order_payload(order_type="dine_in"), format="json")

        assert response.status_code == 400
        assert "table" in response.data["errors"]

    def test_takeaway_cannot_have_a_table(self, as_user, customer, table, order_payload):
        response = as_user(customer).post(URL, order_payload(table=table.pk), format="json")

        assert response.status_code == 400
        assert "table" in response.data["errors"]

    def test_delivery_needs_an_address_and_a_phone(self, as_user, customer, order_payload):
        response = as_user(customer).post(URL, order_payload(order_type="delivery"), format="json")

        assert response.status_code == 400
        assert {"delivery_address", "contact_phone"} <= set(response.data["errors"])

    def test_a_delivery_order_keeps_its_details(self, as_user, customer, order_payload):
        payload = order_payload(
            order_type="delivery",
            delivery_address="12 Main Street",
            contact_phone="+25712345678",
        )

        response = as_user(customer).post(URL, payload, format="json")

        assert response.status_code == 201
        assert response.data["delivery_address"] == "12 Main Street"
        assert response.data["contact_phone"] == "+25712345678"

    def test_an_unknown_table_code_is_rejected(self, as_user, customer, order_payload):
        payload = order_payload(order_type="dine_in", table_token="made-up.token")

        response = as_user(customer).post(URL, payload, format="json")

        assert response.status_code == 400
        assert "table_token" in response.data["errors"]

    def test_staff_naming_an_unknown_table_is_rejected(self, as_user, staff_user, order_payload):
        payload = order_payload(order_type="dine_in", table=9999)

        response = as_user(staff_user).post(URL, payload, format="json")

        assert response.status_code == 400
        assert "table" in response.data["errors"]

    def test_a_dine_in_order_opens_the_table(self, as_user, customer, table, order_payload):
        payload = order_payload(order_type="dine_in", table_token=make_token(table))

        response = as_user(customer).post(URL, payload, format="json")

        table.refresh_from_db()
        assert response.status_code == 201
        assert response.data["table_number"] == 1
        assert table.status == TableStatus.OCCUPIED

    def test_staff_enter_an_order_for_a_guest_without_an_account(
        self, as_user, staff_user, table, order_payload
    ):
        payload = order_payload(order_type="dine_in", table=table.pk)

        response = as_user(staff_user).post(URL, payload, format="json")

        assert response.status_code == 201
        assert response.data["customer"] is None
        assert response.data["customer_name"] == ""