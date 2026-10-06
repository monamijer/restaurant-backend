from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Role
from apps.menu.models import Category, MenuItem
from apps.tables.models import Table


@pytest.fixture
def login():
    """Return a client authenticated through the real login endpoint (a real JWT)."""

    def authenticate(email, password):
        client = APIClient()
        response = client.post(
            "/api/auth/login/", {"email": email, "password": password}, format="json"
        )
        assert response.status_code == 200, response.data
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
        return client

    return authenticate


@pytest.fixture
def restaurant_floor(db):
    """A small menu and two tables, enough for the journeys."""
    category = Category.objects.create(name="Mains")
    dish = MenuItem.objects.create(category=category, name="Grilled fish", price=Decimal("12.50"))
    return {
        "dish": dish,
        "table": Table.objects.create(number=1, capacity=4),
        "other_table": Table.objects.create(number=2, capacity=4),
    }


@pytest.fixture
def staff_client(create_user, password, login):
    create_user(email="floor.staff@example.com", role=Role.STAFF)
    return login("floor.staff@example.com", password)