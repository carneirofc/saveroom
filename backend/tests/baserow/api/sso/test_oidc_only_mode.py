from django.test.utils import override_settings
from django.urls import reverse

import pytest
from rest_framework.status import HTTP_200_OK, HTTP_401_UNAUTHORIZED

from baserow.test_utils.oidc import FakeOIDCProvider

VALID_PASSWORD = "thisIsAValidPassword"


@override_settings(BASEROW_OIDC_ONLY=True)
@pytest.mark.django_db
def test_login_options_omit_password_in_oidc_only_mode(api_client):
    idp = FakeOIDCProvider()
    with override_settings(BASEROW_OIDC_ONLY=True, BASEROW_OIDC_PROVIDERS=[idp.config]):
        response = api_client.get(reverse("api:auth_provider:login_options"))

    body = response.json()
    assert "password" not in body
    assert "openid_connect" in body


@override_settings(BASEROW_OIDC_ONLY=True)
@pytest.mark.django_db
def test_non_staff_password_login_refused_in_oidc_only_mode(api_client, data_fixture):
    data_fixture.create_user(email="user@example.com", password=VALID_PASSWORD)

    response = api_client.post(
        reverse("api:user:token_auth"),
        {"email": "user@example.com", "password": VALID_PASSWORD},
        format="json",
    )

    assert response.status_code == HTTP_401_UNAUTHORIZED
    assert response.json()["error"] == "ERROR_AUTH_PROVIDER_DISABLED"


@override_settings(BASEROW_OIDC_ONLY=True)
@pytest.mark.django_db
def test_staff_password_login_allowed_in_oidc_only_mode(api_client, data_fixture):
    # Break-glass: a staff account can still log in with a password.
    data_fixture.create_user(
        email="admin@example.com", password=VALID_PASSWORD, is_staff=True
    )

    response = api_client.post(
        reverse("api:user:token_auth"),
        {"email": "admin@example.com", "password": VALID_PASSWORD},
        format="json",
    )

    assert response.status_code == HTTP_200_OK
    assert "refresh_token" in response.json()


@override_settings(BASEROW_OIDC_ONLY=True)
@pytest.mark.django_db
def test_password_registration_disabled_in_oidc_only_mode(api_client, data_fixture):
    # An existing user means the instance is past the initial-admin-signup state.
    data_fixture.create_user()

    response = api_client.post(
        reverse("api:user:index"),
        {"name": "New", "email": "new@example.com", "password": VALID_PASSWORD},
        format="json",
    )

    assert response.status_code != HTTP_200_OK
    assert response.json()["error"] == "ERROR_DISABLED_SIGNUP"
