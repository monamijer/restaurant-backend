import io
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from apps.menu.models import Category, MenuItem
from apps.orders.models import Order, OrderItem, OrderType

ITEMS_URL = "/api/menu-items/"
CATEGORIES_URL = "/api/categories/"

pytestmark = pytest.mark.django_db


@pytest.fixture
def category():
    return Category.objects.create(name="Mains")


def make_item(category, **overrides):
    values = {"name": "Grilled fish", "price": Decimal("12.50")}
    values.update(overrides)
    return MenuItem.objects.create(category=category, **values)


def item_payload(category, **overrides):
    payload = {"category": category.pk, "name": "Tiramisu", "price": "6.50"}
    payload.update(overrides)
    return payload


def png_upload(name="dish.png"):
    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), "red").save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


class TestReading:
    def test_menu_is_public_and_paginated(self, api_client, category):
        make_item(category)

        response = api_client.get(ITEMS_URL)

        assert response.status_code == 200
        assert response.data["count"] == 1
        assert response.data["results"][0]["category_name"] == "Mains"

    def test_filter_by_category(self, api_client, category):
        desserts = Category.objects.create(name="Desserts")
        make_item(category, name="Grilled fish")
        make_item(desserts, name="Tiramisu")

        response = api_client.get(ITEMS_URL, {"category": desserts.pk})

        assert [item["name"] for item in response.data["results"]] == ["Tiramisu"]

    def test_filter_by_availability(self, api_client, category):
        make_item(category, name="Available dish")
        make_item(category, name="Sold out dish", is_available=False)

        response = api_client.get(ITEMS_URL, {"is_available": "true"})

        assert [item["name"] for item in response.data["results"]] == ["Available dish"]

    def test_filter_by_price_range(self, api_client, category):
        make_item(category, name="Cheap", price=Decimal("5.00"))
        make_item(category, name="Middle", price=Decimal("10.00"))
        make_item(category, name="Pricey", price=Decimal("20.00"))

        response = api_client.get(ITEMS_URL, {"min_price": "8", "max_price": "15"})

        assert [item["name"] for item in response.data["results"]] == ["Middle"]

    def test_search_by_name(self, api_client, category):
        make_item(category, name="Grilled fish")
        make_item(category, name="Chocolate cake")

        response = api_client.get(ITEMS_URL, {"search": "cake"})

        assert [item["name"] for item in response.data["results"]] == ["Chocolate cake"]

    def test_ordering_by_price_descending(self, api_client, category):
        make_item(category, name="Cheap", price=Decimal("5.00"))
        make_item(category, name="Pricey", price=Decimal("20.00"))

        response = api_client.get(ITEMS_URL, {"ordering": "-price"})

        assert response.data["results"][0]["name"] == "Pricey"

    def test_page_size_is_client_adjustable(self, api_client, category):
        for index in range(3):
            make_item(category, name=f"Dish {index}")

        response = api_client.get(ITEMS_URL, {"page_size": 2})

        assert len(response.data["results"]) == 2
        assert response.data["next"] is not None


class TestWriting:
    def test_anonymous_cannot_create(self, api_client, category):
        response = api_client.post(ITEMS_URL, item_payload(category), format="json")

        assert response.status_code == 401

    @pytest.mark.parametrize("user_fixture", ["customer", "staff_user"])
    def test_only_admins_can_create(self, user_fixture, request, as_user, category):
        user = request.getfixturevalue(user_fixture)

        response = as_user(user).post(ITEMS_URL, item_payload(category), format="json")

        assert response.status_code == 403

    def test_admin_creates_an_item_with_a_generated_slug(self, as_user, admin_user, category):
        response = as_user(admin_user).post(ITEMS_URL, item_payload(category), format="json")

        assert response.status_code == 201
        assert response.data["slug"] == "tiramisu"
        assert response.data["price"] == "6.50"

    def test_negative_price_is_rejected(self, as_user, admin_user, category):
        payload = item_payload(category, price="-1.00")

        response = as_user(admin_user).post(ITEMS_URL, payload, format="json")

        assert response.status_code == 400
        assert "price" in response.data["errors"]

    def test_allergens_are_normalised(self, as_user, admin_user, category):
        payload = item_payload(category, allergens=["Gluten", " gluten ", "Nuts", ""])

        response = as_user(admin_user).post(ITEMS_URL, payload, format="json")

        assert response.status_code == 201
        assert response.data["allergens"] == ["gluten", "nuts"]

    def test_too_many_allergens_are_rejected(self, as_user, admin_user, category):
        payload = item_payload(category, allergens=[f"allergen-{n}" for n in range(21)])

        response = as_user(admin_user).post(ITEMS_URL, payload, format="json")

        assert response.status_code == 400
        assert "allergens" in response.data["errors"]


class TestImages:
    def test_a_valid_image_is_accepted(self, as_user, admin_user, category):
        payload = item_payload(category, image=png_upload())

        response = as_user(admin_user).post(ITEMS_URL, payload, format="multipart")

        assert response.status_code == 201
        assert response.data["image"].endswith(".png")

    def test_a_non_image_is_rejected(self, as_user, admin_user, category):
        fake = SimpleUploadedFile("evil.png", b"definitely not an image", content_type="image/png")

        response = as_user(admin_user).post(
            ITEMS_URL, item_payload(category, image=fake), format="multipart"
        )

        assert response.status_code == 400
        assert "image" in response.data["errors"]

    def test_an_oversized_image_is_rejected(self, as_user, admin_user, category, monkeypatch):
        monkeypatch.setattr("apps.core.validators.MAX_IMAGE_BYTES", 10)

        response = as_user(admin_user).post(
            ITEMS_URL, item_payload(category, image=png_upload()), format="multipart"
        )

        assert response.status_code == 400
        assert "image" in response.data["errors"]


class TestAvailability:
    def test_staff_can_toggle_availability(self, as_user, staff_user, category):
        item = make_item(category)

        response = as_user(staff_user).post(
            f"{ITEMS_URL}{item.pk}/set-availability/", {"is_available": False}, format="json"
        )

        assert response.status_code == 200
        item.refresh_from_db()
        assert item.is_available is False

    def test_customers_cannot_toggle_availability(self, as_user, customer, category):
        item = make_item(category)

        response = as_user(customer).post(
            f"{ITEMS_URL}{item.pk}/set-availability/", {"is_available": False}, format="json"
        )

        assert response.status_code == 403

    def test_staff_cannot_edit_other_item_fields(self, as_user, staff_user, category):
        item = make_item(category)

        response = as_user(staff_user).patch(
            f"{ITEMS_URL}{item.pk}/", {"price": "0.01"}, format="json"
        )

        assert response.status_code == 403


class TestDeletion:
    def test_category_with_items_cannot_be_deleted(self, as_user, admin_user, category):
        make_item(category)

        response = as_user(admin_user).delete(f"{CATEGORIES_URL}{category.pk}/")

        assert response.status_code == 409
        assert response.data["code"] == "CONFLICT"

    def test_empty_category_can_be_deleted(self, as_user, admin_user, category):
        response = as_user(admin_user).delete(f"{CATEGORIES_URL}{category.pk}/")

        assert response.status_code == 204
        assert not Category.objects.filter(pk=category.pk).exists()

    def test_item_used_in_an_order_cannot_be_deleted(self, as_user, admin_user, category):
        item = make_item(category)
        order = Order.objects.create(
            order_type=OrderType.TAKEAWAY,
            subtotal=Decimal("12.50"),
            tax_amount=Decimal("0.00"),
            total=Decimal("12.50"),
        )
        OrderItem.objects.create(
            order=order,
            menu_item=item,
            item_name=item.name,
            quantity=1,
            unit_price=Decimal("12.50"),
            subtotal=Decimal("12.50"),
        )

        response = as_user(admin_user).delete(f"{ITEMS_URL}{item.pk}/")

        assert response.status_code == 409