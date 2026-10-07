import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Role

pytestmark = pytest.mark.django_db

MISSING = 999999
EVERYONE = {"anonymous", "customer", "staff", "admin"}
SIGNED_IN = {"customer", "staff", "admin"}
STAFF = {"staff", "admin"}
ADMIN = {"admin"}

# (method, url, roles allowed in). "Allowed" means the request is not turned away by
# authentication or permissions; the endpoint may still answer 400, 404 or 409.
MATRIX = [
    ("get", "/api/settings/", EVERYONE),
    ("patch", "/api/settings/", ADMIN),
    ("get", "/api/categories/", EVERYONE),
    ("post", "/api/categories/", ADMIN),
    ("get", "/api/menu-items/", EVERYONE),
    ("post", "/api/menu-items/", ADMIN),
    ("post", f"/api/menu-items/{MISSING}/set-availability/", STAFF),
    ("get", "/api/tables/", SIGNED_IN),
    ("post", "/api/tables/", ADMIN),
    ("post", f"/api/tables/{MISSING}/set-status/", STAFF),
    ("get", "/api/reservations/", SIGNED_IN),
    ("get", "/api/reservations/availability/", SIGNED_IN),
    ("post", f"/api/reservations/{MISSING}/confirm/", STAFF),
    ("post", f"/api/reservations/{MISSING}/reject/", STAFF),
    ("post", f"/api/reservations/{MISSING}/complete/", STAFF),
    ("post", f"/api/reservations/{MISSING}/no-show/", STAFF),
    ("post", f"/api/reservations/{MISSING}/cancel/", SIGNED_IN),
    ("get", "/api/queue/", SIGNED_IN),
    ("get", "/api/queue/summary/", EVERYONE),
    ("post", "/api/queue/call-next/", STAFF),
    ("post", f"/api/queue/{MISSING}/call/", STAFF),
    ("post", f"/api/queue/{MISSING}/seat/", STAFF),
    ("post", f"/api/queue/{MISSING}/no-show/", STAFF),
    ("post", f"/api/queue/{MISSING}/cancel/", SIGNED_IN),
    ("get", "/api/orders/", SIGNED_IN),
    ("post", f"/api/orders/{MISSING}/update-status/", STAFF),
    ("post", f"/api/orders/{MISSING}/cancel/", SIGNED_IN),
    ("get", "/api/payments/", SIGNED_IN),
    ("post", f"/api/payments/{MISSING}/confirm/", STAFF),
    ("post", f"/api/payments/{MISSING}/cancel/", SIGNED_IN),
    ("get", "/api/invoices/", SIGNED_IN),
    ("get", f"/api/invoices/{MISSING}/download-pdf/", SIGNED_IN),
    ("get", "/api/notifications/", SIGNED_IN),
    ("get", "/api/notifications/unread-count/", SIGNED_IN),
    ("get", "/api/auth/me/", SIGNED_IN),
    ("get", "/api/users/", STAFF),
    ("post", "/api/users/", ADMIN),
    ("patch", f"/api/users/{MISSING}/", ADMIN),
    ("post", f"/api/users/{MISSING}/set-password/", ADMIN),
    ("post", "/api/auth/change-password/", SIGNED_IN),
    ("get", "/api/dashboard/stats/", STAFF),
    ("get", "/api/reports/revenue/", ADMIN),
    ("get", "/api/reports/order-volume/", ADMIN),
    ("get", "/api/reports/top-items/", ADMIN),
    ("get", "/api/reports/peak-hours/", ADMIN),
    ("get", "/api/reports/table-utilization/", ADMIN),
    ("get", "/api/reports/payments/", ADMIN),
    ("post", "/api/auth/password-reset/", EVERYONE),
    ("post", "/api/auth/password-reset/confirm/", EVERYONE),
    ("post", "/api/tables/resolve-qr/", EVERYONE),
    ("get", f"/api/tables/{MISSING}/qr-code/", ADMIN),
    ("get", "/api/tables/qr-sheet/", ADMIN),
    ("post", f"/api/tables/{MISSING}/regenerate-qr/", ADMIN),    
]


@pytest.fixture
def clients(customer, staff_user, admin_user):
    """One client per role; the anonymous one carries no credentials."""
    built = {"anonymous": APIClient()}
    for role, user in (("customer", customer), ("staff", staff_user), ("admin", admin_user)):
        client = APIClient()
        client.force_authenticate(user=user)
        built[role] = client
    return built


@pytest.mark.parametrize(("method", "url", "allowed"), MATRIX, ids=lambda v: v if isinstance(v, str) else "")
def test_every_role_gets_exactly_the_access_it_should(clients, method, url, allowed):
    for role, client in clients.items():
        status = getattr(client, method)(url, {}, format="json").status_code

        if role in allowed:
            assert status not in (401, 403), f"{role} was refused on {method.upper()} {url}"
        elif role == "anonymous":
            assert status == 401, f"anonymous reached {method.upper()} {url} ({status})"
        else:
            assert status == 403, f"{role} reached {method.upper()} {url} ({status})"


def test_the_matrix_covers_every_role_value():
    assert {Role.CLIENT, Role.STAFF, Role.ADMIN} == {"client", "staff", "admin"}