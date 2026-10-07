import pytest

from apps.orders.models import Order
from apps.tables import qr
from apps.tables.models import Table, TableStatus

ORDERS_URL = "/api/orders/"
TABLES_URL = "/api/tables/"

pytestmark = pytest.mark.django_db


@pytest.fixture
def table():
    return Table.objects.create(number=4, capacity=4, location="Terrace")


@pytest.fixture
def dish(db):
    from decimal import Decimal

    from apps.menu.models import Category, MenuItem

    return MenuItem.objects.create(
        category=Category.objects.create(name="Mains"), name="Grilled fish", price=Decimal("12.50")
    )


def dine_in(dish, **extra):
    payload = {"order_type": "dine_in", "items": [{"menu_item": dish.pk, "quantity": 1}]}
    payload.update(extra)
    return payload


class TestTokens:
    def test_a_token_resolves_back_to_its_table(self, table):
        assert qr.resolve_token(qr.make_token(table)) == table

    def test_the_scan_url_points_at_the_frontend(self, table, settings):
        url = qr.scan_url(table)

        assert url.startswith(f"{settings.FRONTEND_URL}/scan?t=")
        assert qr.resolve_token(url.split("?t=", 1)[1]) == table

    def test_a_tampered_token_is_refused(self, table):
        from rest_framework.exceptions import ValidationError

        with pytest.raises(ValidationError):
            qr.resolve_token(qr.make_token(table)[:-2] + "zz")


class TestOrderingOnSite:
    def test_a_customer_orders_by_scanning_the_code(self, as_user, customer, table, dish):
        payload = dine_in(dish, table_token=qr.make_token(table))

        response = as_user(customer).post(ORDERS_URL, payload, format="json")

        table.refresh_from_db()
        assert response.status_code == 201
        assert response.data["table"] == table.pk
        assert table.status == TableStatus.OCCUPIED

    def test_a_customer_cannot_name_a_table_directly(self, as_user, customer, table, dish):
        response = as_user(customer).post(ORDERS_URL, dine_in(dish, table=table.pk), format="json")

        assert response.status_code == 400
        assert "table" in response.data["errors"]
        assert Order.objects.count() == 0

    def test_a_customer_must_scan_to_dine_in(self, as_user, customer, dish):
        response = as_user(customer).post(ORDERS_URL, dine_in(dish), format="json")

        assert response.status_code == 400
        assert "table_token" in response.data["errors"]

    def test_a_forged_token_is_refused(self, as_user, customer, dish):
        response = as_user(customer).post(
            ORDERS_URL, dine_in(dish, table_token="made-up.token.value"), format="json"
        )

        assert response.status_code == 400
        assert "table_token" in response.data["errors"]

    def test_a_replaced_code_stops_working(self, as_user, admin_user, customer, table, dish):
        old_token = qr.make_token(table)
        as_user(admin_user).post(f"{TABLES_URL}{table.pk}/regenerate-qr/")

        response = as_user(customer).post(
            ORDERS_URL, dine_in(dish, table_token=old_token), format="json"
        )

        assert response.status_code == 400
        assert "table_token" in response.data["errors"]

    def test_a_code_for_a_deleted_table_is_refused(self, as_user, customer, table, dish):
        token = qr.make_token(table)
        table.delete()

        response = as_user(customer).post(
            ORDERS_URL, dine_in(dish, table_token=token), format="json"
        )

        assert response.status_code == 400

    def test_a_token_and_a_table_together_are_refused(self, as_user, customer, table, dish):
        payload = dine_in(dish, table=table.pk, table_token=qr.make_token(table))

        response = as_user(customer).post(ORDERS_URL, payload, format="json")

        assert response.status_code == 400

    def test_staff_can_still_name_the_table(self, as_user, staff_user, table, dish):
        response = as_user(staff_user).post(ORDERS_URL, dine_in(dish, table=table.pk), format="json")

        assert response.status_code == 201

    def test_a_dine_in_order_from_staff_without_a_table_is_refused(
        self, as_user, staff_user, dish
    ):
        response = as_user(staff_user).post(ORDERS_URL, dine_in(dish), format="json")

        assert response.status_code == 400
        assert "table" in response.data["errors"]


class TestResolvingAScan:
    def test_anyone_can_resolve_a_scanned_code(self, api_client, table):
        response = api_client.post(
            f"{TABLES_URL}resolve-qr/", {"token": qr.make_token(table)}, format="json"
        )

        assert response.status_code == 200
        assert response.data == {"id": table.pk, "number": 4, "capacity": 4, "location": "Terrace"}

    def test_an_invalid_code_is_refused(self, api_client):
        response = api_client.post(f"{TABLES_URL}resolve-qr/", {"token": "nope"}, format="json")

        assert response.status_code == 400
        assert "token" in response.data["errors"]


class TestAdministratorTools:
    def test_an_admin_downloads_a_table_code_as_a_png(self, as_user, admin_user, table):
        response = as_user(admin_user).get(f"{TABLES_URL}{table.pk}/qr-code/")

        assert response.status_code == 200
        assert response["Content-Type"] == "image/png"
        assert "table-4-qr.png" in response["Content-Disposition"]
        assert "no-store" in response["Cache-Control"]
        assert response.content.startswith(b"\x89PNG")

    def test_the_images_are_never_written_to_public_media(
        self, as_user, admin_user, table, settings
    ):
        as_user(admin_user).get(f"{TABLES_URL}{table.pk}/qr-code/")
        as_user(admin_user).get(f"{TABLES_URL}qr-sheet/")

        assert not settings.MEDIA_ROOT.exists() or not any(settings.MEDIA_ROOT.rglob("*"))

    def test_an_admin_prints_every_code_on_a_sheet(self, as_user, admin_user, table):
        for number in range(5, 12):
            Table.objects.create(number=number, capacity=2)

        response = as_user(admin_user).get(f"{TABLES_URL}qr-sheet/")

        assert response.status_code == 200
        assert response["Content-Type"] == "application/pdf"
        assert response.content.startswith(b"%PDF")

    def test_printing_without_tables_is_a_conflict(self, as_user, admin_user):
        assert as_user(admin_user).get(f"{TABLES_URL}qr-sheet/").status_code == 409

    def test_regenerating_makes_the_old_token_invalid_and_the_new_one_work(
        self, as_user, admin_user, table
    ):
        old_token = qr.make_token(table)

        response = as_user(admin_user).post(f"{TABLES_URL}{table.pk}/regenerate-qr/")

        table.refresh_from_db()
        assert response.status_code == 200
        assert table.qr_version == 2
        assert qr.resolve_token(qr.make_token(table)) == table
        with pytest.raises(Exception):
            qr.resolve_token(old_token)

    @pytest.mark.parametrize("user_fixture", ["customer", "staff_user"])
    def test_only_admins_manage_codes(self, request, as_user, table, user_fixture):
        client = as_user(request.getfixturevalue(user_fixture))

        assert client.get(f"{TABLES_URL}{table.pk}/qr-code/").status_code == 403
        assert client.get(f"{TABLES_URL}qr-sheet/").status_code == 403
        assert client.post(f"{TABLES_URL}{table.pk}/regenerate-qr/").status_code == 403

    def test_tables_no_longer_expose_a_stored_image(self, as_user, staff_user, table):
        response = as_user(staff_user).get(f"{TABLES_URL}{table.pk}/")

        assert "qr_code" not in response.data