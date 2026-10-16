from datetime import timedelta
from urllib.parse import parse_qs, urlparse

from django.conf import settings
from django.core.cache import cache
from django.test.utils import override_settings
from django.urls import reverse

import pytest
import responses
from freezegun import freeze_time
from rest_framework_simplejwt.tokens import RefreshToken

from baserow.core.auth_provider.models import OIDCAuthProviderModel
from baserow.core.sso.oidc.handler import SESSION_NONCE_KEY, SESSION_STATE_KEY
from baserow.test_utils.oidc import FakeOIDCProvider


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.mark.django_db
def test_login_options_lists_oidc_providers(api_client):
    idp = FakeOIDCProvider()
    with override_settings(BASEROW_OIDC_PROVIDERS=[idp.config]):
        response = api_client.get(reverse("api:auth_provider:login_options"))

    assert response.status_code == 200
    body = response.json()
    assert "openid_connect" in body
    oidc = body["openid_connect"]
    assert oidc["type"] == "openid_connect"
    assert len(oidc["items"]) == 1
    item = oidc["items"][0]
    assert item["type"] == "openid_connect"
    assert item["name"] == "Keycloak"
    assert item["redirect_url"].endswith("/api/sso/oidc/login/keycloak/")
    # A single provider auto-redirects.
    assert oidc["default_redirect_url"] == item["redirect_url"]


@pytest.mark.django_db
def test_login_options_omits_oidc_when_unconfigured(api_client):
    with override_settings(BASEROW_OIDC_PROVIDERS=[]):
        response = api_client.get(reverse("api:auth_provider:login_options"))

    assert response.status_code == 200
    assert "openid_connect" not in response.json()


@pytest.mark.django_db
def test_login_options_lists_multiple_providers(api_client):
    idp = FakeOIDCProvider()
    second = FakeOIDCProvider(name="google", display_name="Google")
    with override_settings(BASEROW_OIDC_PROVIDERS=[idp.config, second.config]):
        response = api_client.get(reverse("api:auth_provider:login_options"))

    oidc = response.json()["openid_connect"]
    assert [i["name"] for i in oidc["items"]] == ["Keycloak", "Google"]
    # More than one provider => no default auto-redirect.
    assert oidc["default_redirect_url"] is None


@responses.activate(assert_all_requests_are_fired=False)
@pytest.mark.django_db
def test_login_redirects_to_provider(api_client):
    idp = FakeOIDCProvider()
    responses.add(responses.GET, idp.discovery_url, json=idp.discovery_document())

    with override_settings(BASEROW_OIDC_PROVIDERS=[idp.config]):
        response = api_client.get(
            reverse("api:sso:oidc:login", args=("keycloak",)) + "?original=/dashboard"
        )

    assert response.status_code == 302
    assert response.headers["Location"].startswith(idp.authorization_endpoint)


@pytest.mark.django_db
def test_login_unknown_provider_redirects_to_error(api_client):
    with override_settings(BASEROW_OIDC_PROVIDERS=[]):
        response = api_client.get(reverse("api:sso:oidc:login", args=("nope",)))

    assert response.status_code == 302
    assert "/login?" in response.headers["Location"]
    assert "errorProviderDoesNotExist" in response.headers["Location"]


def _drive_callback(api_client, idp, responses_mock):
    """Runs login then callback against the same client session; returns the response."""

    responses_mock.add(
        responses_mock.GET, idp.discovery_url, json=idp.discovery_document()
    )
    api_client.get(reverse("api:sso:oidc:login", args=(idp.name,)))
    nonce = api_client.session[SESSION_NONCE_KEY]
    idp.register_all(responses_mock, nonce=nonce)
    return api_client.get(
        reverse("api:sso:oidc:callback", args=(idp.name,))
        + f"?code=the-code&state={api_client.session[SESSION_STATE_KEY]}"
    )


@responses.activate(assert_all_requests_are_fired=False)
@pytest.mark.django_db
def test_callback_creates_user_and_signs_in(api_client):
    from django.contrib.auth import get_user_model

    User = get_user_model()
    idp = FakeOIDCProvider(email="newuser@example.com", full_name="New User")

    with override_settings(BASEROW_OIDC_PROVIDERS=[idp.config]):
        response = _drive_callback(api_client, idp, responses)

    assert response.status_code == 302
    location = response.headers["Location"]
    # The refresh token is embedded in the redirect for the SPA to pick up.
    query = parse_qs(urlparse(location).query)
    assert "token" in query
    assert "user_session" in query

    user = User.objects.get(email="newuser@example.com")
    assert user.first_name == "New User"
    # The provider anchor row now links the created user.
    provider = OIDCAuthProviderModel.objects.get(name="keycloak")
    assert provider.users.filter(id=user.id).exists()


@responses.activate(assert_all_requests_are_fired=False)
@pytest.mark.django_db
def test_callback_signs_in_existing_user(api_client, data_fixture):
    idp = FakeOIDCProvider(email="existing@example.com", full_name="Existing User")
    # Pre-create the user and link them to the provider anchor so the
    # different-provider guard is satisfied.
    user = data_fixture.create_user(email="existing@example.com")
    provider = OIDCAuthProviderModel.objects.create(name=idp.name)
    provider.users.add(user)

    with override_settings(BASEROW_OIDC_PROVIDERS=[idp.config]):
        response = _drive_callback(api_client, idp, responses)

    assert response.status_code == 302
    assert "error=" not in response.headers["Location"]
    query = parse_qs(urlparse(response.headers["Location"]).query)
    assert "token" in query


@responses.activate(assert_all_requests_are_fired=False)
@pytest.mark.django_db
def test_callback_with_a_mismatched_state_redirects_to_error(api_client):
    idp = FakeOIDCProvider()
    responses.add(responses.GET, idp.discovery_url, json=idp.discovery_document())

    with override_settings(BASEROW_OIDC_PROVIDERS=[idp.config]):
        api_client.get(reverse("api:sso:oidc:login", args=(idp.name,)))
        idp.register_all(responses, nonce=api_client.session[SESSION_NONCE_KEY])
        response = api_client.get(
            reverse("api:sso:oidc:callback", args=(idp.name,))
            + "?code=the-code&state=forged"
        )

    assert response.status_code == 302
    assert "errorAuthFlowError" in response.headers["Location"]


@responses.activate(assert_all_requests_are_fired=False)
@pytest.mark.django_db
def test_callback_refuses_an_unverified_email(api_client):
    from django.contrib.auth import get_user_model

    idp = FakeOIDCProvider(email="unverified@example.com")
    responses.add(responses.GET, idp.discovery_url, json=idp.discovery_document())

    with override_settings(BASEROW_OIDC_PROVIDERS=[idp.config]):
        api_client.get(reverse("api:sso:oidc:login", args=(idp.name,)))
        idp.register_all(
            responses,
            nonce=api_client.session[SESSION_NONCE_KEY],
            userinfo_extra={"email_verified": False},
        )
        response = api_client.get(
            reverse("api:sso:oidc:callback", args=(idp.name,))
            + f"?code=the-code&state={api_client.session[SESSION_STATE_KEY]}"
        )

    assert response.status_code == 302
    assert "errorEmailNotVerified" in response.headers["Location"]
    assert not get_user_model().objects.filter(email="unverified@example.com").exists()


def _refresh_token_lifetime(response):
    token = parse_qs(urlparse(response.headers["Location"]).query)["token"][0]
    refresh = RefreshToken(token)
    return timedelta(seconds=refresh["exp"] - refresh["iat"])


@responses.activate(assert_all_requests_are_fired=False)
@pytest.mark.django_db
def test_callback_bounds_the_session_to_the_provider_lifetime(api_client):
    idp = FakeOIDCProvider(session_lifetime_minutes=30)

    with override_settings(BASEROW_OIDC_PROVIDERS=[idp.config]):
        response = _drive_callback(api_client, idp, responses)

    assert _refresh_token_lifetime(response) == timedelta(minutes=30)


@responses.activate(assert_all_requests_are_fired=False)
@pytest.mark.django_db
def test_callback_without_a_provider_lifetime_uses_the_global_one(api_client):
    idp = FakeOIDCProvider(session_lifetime_minutes=None)

    with override_settings(BASEROW_OIDC_PROVIDERS=[idp.config]):
        response = _drive_callback(api_client, idp, responses)

    assert _refresh_token_lifetime(response) == settings.REFRESH_TOKEN_LIFETIME


@responses.activate(assert_all_requests_are_fired=False)
@pytest.mark.django_db
def test_sso_session_cannot_be_refreshed_past_its_lifetime(api_client):
    idp = FakeOIDCProvider(session_lifetime_minutes=30)

    with freeze_time("2026-01-01 09:00"):
        with override_settings(BASEROW_OIDC_PROVIDERS=[idp.config]):
            response = _drive_callback(api_client, idp, responses)
        token = parse_qs(urlparse(response.headers["Location"]).query)["token"][0]

    with freeze_time("2026-01-01 09:20"):
        ok = api_client.post(
            reverse("api:user:token_refresh"), {"refresh_token": token}, format="json"
        )
    with freeze_time("2026-01-01 09:31"):
        expired = api_client.post(
            reverse("api:user:token_refresh"), {"refresh_token": token}, format="json"
        )

    assert ok.status_code == 200
    assert expired.status_code == 401
