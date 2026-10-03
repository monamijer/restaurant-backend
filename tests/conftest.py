import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.accounts.models import Role, User

STRONG_PASSWORD = "S3cure-Passw0rd!"
FAST_TEST_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


@pytest.fixture(autouse=True)
def isolated_environment(settings, tmp_path):
    """Each test gets empty throttle counters, a private media folder and a fast hasher."""
    settings.SECURE_SSL_REDIRECT = False
    settings.PASSWORD_HASHERS = FAST_TEST_HASHERS  # PBKDF2 is deliberately slow
    settings.MEDIA_ROOT = tmp_path / "media"
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
