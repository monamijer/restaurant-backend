import re

import pytest
from rest_framework.test import APIClient

REQUEST_URL = "/api/auth/password-reset/"
CONFIRM_URL = "/api/auth/password-reset/confirm/"
NEW_PASSWORD = "Fresh-Start-Passw0rd!"
LINK_PATTERN = re.compile(r"uid=([^&\s]+)&token=([^\s]+)")

pytestmark = pytest.mark.django_db


def ask_for_reset(client, email):
    return client.post(REQUEST_URL, {"email": email}, format="json")


def link_parts(mailbox):
    """The (uid, token) of the link in the last e-mail sent."""
    return LINK_PATTERN.search(mailbox[-1].body).groups()


def confirm(client, uid, token, new_password=NEW_PASSWORD):
    return client.post(
        CONFIRM_URL, {"uid": uid, "token": token, "new_password": new_password}, format="json"
    )


def login(email, password):
    return APIClient().post(
        "/api/auth/login/", {"email": email, "password": password}, format="json"
    )


class TestRequestingAReset:
    def test_an_existing_account_receives_a_link(self, api_client, customer, mailoutbox, settings):
        response = ask_for_reset(api_client, customer.email)

        assert response.status_code == 200
        assert len(mailoutbox) == 1
        assert mailoutbox[0].to == [customer.email]
        assert settings.FRONTEND_URL in mailoutbox[0].body
        assert "Bonjour" in mailoutbox[0].body and "Hello" in mailoutbox[0].body

    def test_an_unknown_address_gets_the_same_answer_and_no_mail(
        self, api_client, customer, mailoutbox
    ):
        known = ask_for_reset(api_client, customer.email)
        unknown = ask_for_reset(api_client, "nobody@example.com")

        assert unknown.status_code == known.status_code == 200
        assert unknown.data == known.data
        assert len(mailoutbox) == 1  # Only the known address received something.

    def test_an_inactive_account_gets_no_mail(self, api_client, create_user, mailoutbox):
        create_user(email="suspended@example.com", is_active=False)

        response = ask_for_reset(api_client, "suspended@example.com")

        assert response.status_code == 200
        assert mailoutbox == []

    def test_the_address_is_matched_case_insensitively(self, api_client, customer, mailoutbox):
        ask_for_reset(api_client, customer.email.upper())

        assert len(mailoutbox) == 1

    def test_a_broken_mail_server_does_not_change_the_answer(
        self, api_client, customer, monkeypatch
    ):
        def fail(*args, **kwargs):
            raise ConnectionError("SMTP is down")

        monkeypatch.setattr("apps.accounts.password_reset.send_mail", fail)

        response = ask_for_reset(api_client, customer.email)

        assert response.status_code == 200

    def test_requests_are_throttled(self, api_client, customer):
        statuses = [ask_for_reset(api_client, customer.email).status_code for _ in range(6)]

        assert statuses == [200, 200, 200, 200, 200, 429]

    def test_a_malformed_address_is_rejected(self, api_client):
        response = ask_for_reset(api_client, "not-an-email")

        assert response.status_code == 400


class TestConfirmingAReset:
    def test_the_link_sets_a_new_password(self, api_client, customer, mailoutbox, password):
        ask_for_reset(api_client, customer.email)
        uid, token = link_parts(mailoutbox)

        response = confirm(api_client, uid, token)

        assert response.status_code == 204
        assert login(customer.email, password).status_code == 401
        assert login(customer.email, NEW_PASSWORD).status_code == 200

    def test_a_link_can_only_be_used_once(self, api_client, customer, mailoutbox):
        ask_for_reset(api_client, customer.email)
        uid, token = link_parts(mailoutbox)
        confirm(api_client, uid, token)

        again = confirm(api_client, uid, token, "Another-Passw0rd-Entirely!")

        assert again.status_code == 400
        assert "token" in again.data["errors"]

    def test_a_weak_password_is_refused_and_the_link_stays_valid(
        self, api_client, customer, mailoutbox
    ):
        ask_for_reset(api_client, customer.email)
        uid, token = link_parts(mailoutbox)

        weak = confirm(api_client, uid, token, "12345678")
        retry = confirm(api_client, uid, token)

        assert weak.status_code == 400
        assert "new_password" in weak.data["errors"]
        assert retry.status_code == 204

    def test_a_tampered_token_is_refused(self, api_client, customer, mailoutbox):
        ask_for_reset(api_client, customer.email)
        uid, token = link_parts(mailoutbox)

        response = confirm(api_client, uid, token[:-3] + "xyz")

        assert response.status_code == 400
        assert "token" in response.data["errors"]

    @pytest.mark.parametrize("uid", ["not-base64!!", "MQ"])
    def test_a_bad_identifier_gives_the_same_generic_error(self, api_client, customer, uid):
        response = confirm(api_client, uid, "whatever-token")

        assert response.status_code == 400
        assert "token" in response.data["errors"]

    def test_an_expired_link_is_refused(self, api_client, customer, mailoutbox, settings):
        ask_for_reset(api_client, customer.email)
        uid, token = link_parts(mailoutbox)
        settings.PASSWORD_RESET_TIMEOUT = -1

        response = confirm(api_client, uid, token)

        assert response.status_code == 400

    def test_a_deactivated_account_cannot_use_its_link(
        self, api_client, customer, mailoutbox
    ):
        ask_for_reset(api_client, customer.email)
        uid, token = link_parts(mailoutbox)
        customer.is_active = False
        customer.save()

        response = confirm(api_client, uid, token)

        assert response.status_code == 400

    def test_resetting_signs_the_user_out_everywhere(
        self, api_client, customer, mailoutbox, password
    ):
        old_refresh = login(customer.email, password).data["refresh"]
        ask_for_reset(api_client, customer.email)
        uid, token = link_parts(mailoutbox)

        confirm(api_client, uid, token)

        refreshed = APIClient().post("/api/auth/refresh/", {"refresh": old_refresh}, format="json")
        assert refreshed.status_code == 401