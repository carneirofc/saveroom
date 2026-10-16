from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test.utils import override_settings
from django.urls import reverse

import pytest
import responses

from baserow.core.auth_provider.models import OIDCAuthProviderModel
from baserow.core.sso.oidc.handler import SESSION_NONCE_KEY, SESSION_STATE_KEY
from baserow.core.user.exceptions import DisabledSignupError
from baserow.test_utils.oidc import FakeOIDCProvider

EMAIL = "existing@example.com"


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


def _drive_callback(api_client, idp, responses_mock, userinfo_extra=None):
    responses_mock.add(
        responses_mock.GET, idp.discovery_url, json=idp.discovery_document()
    )
    api_client.get(reverse("api:sso:oidc:login", args=(idp.name,)))
    idp.register_all(
        responses_mock,
        nonce=api_client.session[SESSION_NONCE_KEY],
        userinfo_extra=userinfo_extra,
    )
    return api_client.get(
        reverse("api:sso:oidc:callback", args=(idp.name,))
        + f"?code=the-code&state={api_client.session[SESSION_STATE_KEY]}"
    )


def _is_linked(user, idp):
    return OIDCAuthProviderModel.objects.filter(name=idp.name, users=user).exists()


@responses.activate(assert_all_requests_are_fired=False)
@pytest.mark.django_db
def test_existing_account_is_refused_without_linking(api_client, data_fixture):
    user = data_fixture.create_user(email=EMAIL)
    idp = FakeOIDCProvider(email=EMAIL)

    with override_settings(BASEROW_OIDC_PROVIDERS=[idp.config]):
        response = _drive_callback(api_client, idp, responses)

    assert "errorDifferentProvider" in response.headers["Location"]
    assert not _is_linked(user, idp)


@responses.activate(assert_all_requests_are_fired=False)
@pytest.mark.django_db
def test_existing_account_is_linked_when_the_provider_allows_it(
    api_client, data_fixture
):
    user = data_fixture.create_user(email=EMAIL)
    idp = FakeOIDCProvider(email=EMAIL, link_existing_accounts=True)

    with override_settings(BASEROW_OIDC_PROVIDERS=[idp.config]):
        response = _drive_callback(api_client, idp, responses)

    assert response.status_code == 302
    assert "error=" not in response.headers["Location"]
    assert "token" in parse_qs(urlparse(response.headers["Location"]).query)
    assert _is_linked(user, idp)
    assert get_user_model().objects.filter(email=EMAIL).count() == 1


@responses.activate(assert_all_requests_are_fired=False)
@pytest.mark.django_db
def test_unverified_email_is_not_linked_even_when_verification_is_optional(
    api_client, data_fixture
):
    user = data_fixture.create_user(email=EMAIL)
    idp = FakeOIDCProvider(
        email=EMAIL, link_existing_accounts=True, require_verified_email=False
    )

    with override_settings(BASEROW_OIDC_PROVIDERS=[idp.config]):
        response = _drive_callback(
            api_client, idp, responses, userinfo_extra={"email_verified": False}
        )

    assert "errorDifferentProvider" in response.headers["Location"]
    assert not _is_linked(user, idp)


@responses.activate(assert_all_requests_are_fired=False)
@pytest.mark.django_db
@pytest.mark.parametrize("flag", ["is_staff", "is_superuser"])
def test_privileged_account_is_never_auto_linked(api_client, data_fixture, flag):
    user = data_fixture.create_user(email=EMAIL, **{flag: True})
    idp = FakeOIDCProvider(email=EMAIL, link_existing_accounts=True)

    with override_settings(BASEROW_OIDC_PROVIDERS=[idp.config]):
        response = _drive_callback(api_client, idp, responses)

    assert "errorDifferentProvider" in response.headers["Location"]
    assert not _is_linked(user, idp)


@responses.activate(assert_all_requests_are_fired=False)
@pytest.mark.django_db
def test_link_is_rolled_back_when_sign_in_is_refused_later(api_client, data_fixture):
    user = data_fixture.create_user(email=EMAIL)
    idp = FakeOIDCProvider(email=EMAIL, link_existing_accounts=True)

    # Refuse after the account was linked, inside the same transaction.
    with (
        override_settings(BASEROW_OIDC_PROVIDERS=[idp.config]),
        patch(
            "baserow.api.sso.oidc.views.sync_global_roles",
            side_effect=DisabledSignupError(),
        ),
    ):
        response = _drive_callback(api_client, idp, responses)

    assert "errorSignupDisabled" in response.headers["Location"]
    assert not _is_linked(user, idp)
