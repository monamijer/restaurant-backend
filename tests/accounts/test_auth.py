import pytest

from apps.accounts.models import User

REGISTER_URL = "/api/auth/register/"
LOGIN_URL = "/api/auth/login/"
REFRESH_URL = "/api/auth/refresh/"
LOGOUT_URL = "/api/auth/logout/"
ME_URL = "/api/auth/me/"

AUTH_THROTTLE_LIMIT = 10


def registration_payload(password, **overrides):
    payload = {
        "email": "grace@example.com",
        "password": password,
        "first_name": "Grace",
        "last_name": "Hopper",
    }
    payload.update(overrides)
    return payload


def login(api_client, email, password):
    return api_client.post(LOGIN_URL, {"email": email, "password": password}, format="json")


def authenticate(api_client, access_token):
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")


@pytest.mark.django_db
class TestRegistration:
    def test_creates_client_account_with_hashed_password(self, api_client, password):
        response = api_client.post(REGISTER_URL, registration_payload(password), format="json")

        assert response.status_code == 201
        assert "password" not in response.data
        assert response.data["role"] == "client"
        user = User.objects.get(email="grace@example.com")
        assert user.password != password
        assert user.check_password(password)

    def test_ignores_role_escalation_attempt(self, api_client, password):
        payload = registration_payload(password, role="admin")

        response = api_client.post(REGISTER_URL, payload, format="json")

        assert response.status_code == 201
        assert User.objects.get(email="grace@example.com").role == "client"

    def test_rejects_duplicate_email_case_insensitively(self, api_client, create_user, password):
        create_user(email="taken@example.com")

        response = api_client.post(
            REGISTER_URL, registration_payload(password, email="TAKEN@example.com"), format="json"
        )

        assert response.status_code == 400
        assert response.data["success"] is False
        assert response.data["code"] == "VALIDATION_ERROR"
        assert "email" in response.data["errors"]

    def test_rejects_weak_password(self, api_client):
        response = api_client.post(REGISTER_URL, registration_payload("12345678"), format="json")

        assert response.status_code == 400
        assert "password" in response.data["errors"]


@pytest.mark.django_db
class TestLogin:
    def test_returns_tokens_and_profile(self, api_client, create_user, password):
        create_user(email="customer@example.com")

        response = login(api_client, "customer@example.com", password)

        assert response.status_code == 200
        assert response.data["access"]
        assert response.data["refresh"]
        assert response.data["user"]["email"] == "customer@example.com"
        assert response.data["user"]["role"] == "client"

    def test_email_is_case_insensitive(self, api_client, create_user, password):
        create_user(email="customer@example.com")

        response = login(api_client, "Customer@Example.COM", password)

        assert response.status_code == 200

    def test_wrong_password_returns_401_envelope(self, api_client, create_user):
        create_user()

        response = login(api_client, "customer@example.com", "wrong-password")

        assert response.status_code == 401
        assert response.data["success"] is False
        assert response.data["code"] == "AUTHENTICATION_FAILED"

    def test_inactive_user_cannot_login(self, api_client, create_user, password):
        create_user(is_active=False)

        response = login(api_client, "customer@example.com", password)

        assert response.status_code == 401

    def test_repeated_attempts_are_throttled(self, api_client, create_user):
        create_user()

        for _ in range(AUTH_THROTTLE_LIMIT):
            login(api_client, "customer@example.com", "wrong-password")
        response = login(api_client, "customer@example.com", "wrong-password")

        assert response.status_code == 429
        assert response.data["code"] == "THROTTLED"


@pytest.mark.django_db
class TestCurrentUser:
    def test_requires_authentication(self, api_client):
        response = api_client.get(ME_URL)

        assert response.status_code == 401
        assert response.data["code"] == "AUTHENTICATION_FAILED"

    def test_returns_own_profile(self, api_client, create_user, password):
        create_user(email="customer@example.com")
        authenticate(api_client, login(api_client, "customer@example.com", password).data["access"])

        response = api_client.get(ME_URL)

        assert response.status_code == 200
        assert response.data["email"] == "customer@example.com"

    def test_patch_updates_profile_but_not_role_or_email(self, api_client, create_user, password):
        create_user(email="customer@example.com")
        authenticate(api_client, login(api_client, "customer@example.com", password).data["access"])

        response = api_client.patch(
            ME_URL,
            {"first_name": "Changed", "role": "admin", "email": "hacker@example.com"},
            format="json",
        )

        assert response.status_code == 200
        user = User.objects.get(pk=response.data["id"])
        assert user.first_name == "Changed"
        assert user.role == "client"
        assert user.email == "customer@example.com"


@pytest.mark.django_db
class TestTokenLifecycle:
    def test_refresh_rotates_and_blacklists_the_old_token(self, api_client, create_user, password):
        create_user()
        old_refresh = login(api_client, "customer@example.com", password).data["refresh"]

        rotated = api_client.post(REFRESH_URL, {"refresh": old_refresh}, format="json")
        reused = api_client.post(REFRESH_URL, {"refresh": old_refresh}, format="json")

        assert rotated.status_code == 200
        assert rotated.data["refresh"] != old_refresh
        assert reused.status_code == 401

    def test_logout_revokes_the_refresh_token(self, api_client, create_user, password):
        create_user()
        refresh = login(api_client, "customer@example.com", password).data["refresh"]

        logout = api_client.post(LOGOUT_URL, {"refresh": refresh}, format="json")
        after = api_client.post(REFRESH_URL, {"refresh": refresh}, format="json")

        assert logout.status_code == 200
        assert after.status_code == 401