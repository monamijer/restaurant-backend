import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.accounts.models import User

STRONG_PASSWORD = "S3cure-Passw0rd!"


@pytest.fixture(autouse=True)
def isolated_environment(settings):
    """Each test starts with no throttle history and no forced HTTPS redirect."""
    settings.SECURE_SSL_REDIRECT = False
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