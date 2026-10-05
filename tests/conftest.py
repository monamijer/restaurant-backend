from decimal import Decimal

import pytest
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.orders.models import Order, OrderStatus, OrderType
from apps.payments.models import Payment, PaymentMethod, PaymentStatus

STRONG_PASSWORD = "S3cure-Passw0rd!"
FAST_TEST_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


@pytest.fixture(autouse=True)
def isolated_environment(settings, tmp_path):
    """Each test gets empty throttle counters, private folders and a fast hasher."""
    settings.SECURE_SSL_REDIRECT = False
    settings.PASSWORD_HASHERS = FAST_TEST_HASHERS  # PBKDF2 is deliberately slow
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.PRIVATE_MEDIA_ROOT = tmp_path / "private"
    settings.ALLOW_SIMULATED_PAYMENTS = True
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def password():
    return STRONG_PASSWORD


@pytest.fixture
def create_user(db, password):
    def factory(email="customer@example.com", **extra):
        raw_password = extra.pop("password", password)
        extra.setdefault("first_name", "Test")
        extra.setdefault("last_name", "Customer")
        return User.objects.create_user(email=email, password=raw_password, **extra)

    return factory


@pytest.fixture
def customer(create_user):
    return create_user(email="customer@example.com", role=Role.CLIENT)


@pytest.fixture
def staff_user(create_user):
    return create_user(email="staff@example.com", role=Role.STAFF)


@pytest.fixture
def admin_user(create_user):
    return create_user(email="admin@example.com", role=Role.ADMIN)


@pytest.fixture
def as_user(api_client):
    """Authenticate the shared client as `user`, bypassing the login throttle."""

    def authenticate(user):
        api_client.force_authenticate(user=user)
        return api_client

    return authenticate


@pytest.fixture
def make_order():
    """Insert an order directly (to arrange state), bypassing the pricing service.

    `paid=True` also records a PAID cash payment covering the total."""

    def factory(
        customer=None,
        *,
        order_type=OrderType.TAKEAWAY,
        status=OrderStatus.PENDING,
        table=None,
        total=Decimal("10.00"),
        paid=False,
    ):
        order = Order.objects.create(
            customer=customer,
            table=table,
            order_type=order_type,
            status=status,
            subtotal=total,
            tax_amount=Decimal("0.00"),
            total=total,
        )
        if paid:
            Payment.objects.create(
                order=order,
                method=PaymentMethod.CASH,
                amount=total,
                status=PaymentStatus.PAID,
                paid_at=timezone.now(),
            )
        return order

    return factory
