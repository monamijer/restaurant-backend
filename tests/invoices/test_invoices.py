from datetime import UTC, datetime

import pytest
from django.conf import settings as django_settings

from apps.invoices.models import Invoice
from apps.menu.models import Category, MenuItem
from apps.orders import services as order_services
from apps.orders.models import OrderType
from apps.payments import services as payment_services
from apps.payments.models import PaymentMethod

URL = "/api/invoices/"
YEAR = datetime.now(UTC).year

pytestmark = pytest.mark.django_db


@pytest.fixture
def pay_card():
    def pay(order, actor):
        return payment_services.start_payment(
            order_id=order.pk, method=PaymentMethod.CARD, token="tok_visa", actor=actor
        )

    return pay


def body(response):
    return b"".join(response.streaming_content)


def test_invoice_numbers_are_sequential(customer, make_order, pay_card):
    first, second = make_order(customer), make_order(customer)

    pay_card(first, customer)
    pay_card(second, customer)

    numbers = list(Invoice.objects.order_by("pk").values_list("invoice_number", flat=True))
    assert numbers == [f"INV-{YEAR}-000001", f"INV-{YEAR}-000002"]


def test_an_invoice_copies_the_order_total_and_belongs_to_one_order(
    customer, make_order, pay_card
):
    order = make_order(customer)
    pay_card(order, customer)

    assert order.invoice.total == order.total


def test_customers_only_see_their_own_invoices(
    as_user, customer, create_user, make_order, pay_card
):
    other = create_user(email="other@example.com")
    mine = make_order(customer)
    pay_card(mine, customer)
    pay_card(make_order(other), other)

    response = as_user(customer).get(URL)

    assert [item["order"] for item in response.data["results"]] == [mine.pk]
    assert response.data["results"][0]["currency"] == "USD"


def test_staff_see_every_invoice(as_user, staff_user, customer, make_order, pay_card):
    pay_card(make_order(customer), customer)
    pay_card(make_order(customer), customer)

    response = as_user(staff_user).get(URL)

    assert response.data["count"] == 2


def test_the_owner_downloads_a_real_pdf(as_user, customer, make_order, pay_card):
    order = make_order(customer)
    pay_card(order, customer)

    response = as_user(customer).get(f"{URL}{order.invoice.pk}/download-pdf/")

    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert f"INV-{YEAR}-000001.pdf" in response["Content-Disposition"]
    assert "no-store" in response["Cache-Control"]
    assert body(response).startswith(b"%PDF")


def test_someone_elses_invoice_cannot_be_downloaded(
    as_user, customer, create_user, make_order, pay_card
):
    other = create_user(email="other@example.com")
    foreign = make_order(other)
    pay_card(foreign, other)

    response = as_user(customer).get(f"{URL}{foreign.invoice.pk}/download-pdf/")

    assert response.status_code == 404


def test_anonymous_cannot_download(api_client, customer, make_order, pay_card):
    order = make_order(customer)
    pay_card(order, customer)

    response = api_client.get(f"{URL}{order.invoice.pk}/download-pdf/")

    assert response.status_code == 401


def test_the_pdf_lives_in_private_storage_with_no_public_url(customer, make_order, pay_card):
    order = make_order(customer)
    pay_card(order, customer)
    invoice = order.invoice

    assert str(invoice.pdf_file.path).startswith(str(django_settings.PRIVATE_MEDIA_ROOT))
    assert not str(invoice.pdf_file.path).startswith(str(django_settings.MEDIA_ROOT))
    with pytest.raises(ValueError):
        invoice.pdf_file.url


def test_special_characters_in_dish_names_do_not_break_the_pdf(
    as_user, customer, pay_card
):
    category = Category.objects.create(name="Mains")
    nasty = MenuItem.objects.create(category=category, name="Fish & <Chips> </b>", price="9.50")
    order = order_services.create_order(
        customer=customer,
        order_type=OrderType.TAKEAWAY,
        lines=[{"menu_item_id": nasty.pk, "quantity": 2}],
    )
    pay_card(order, customer)

    response = as_user(customer).get(f"{URL}{order.invoice.pk}/download-pdf/")

    assert response.status_code == 200
    assert body(response).startswith(b"%PDF")