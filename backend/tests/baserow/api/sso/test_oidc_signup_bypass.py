from urllib.parse import parse_qs, urlparse

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test.utils import override_settings
from django.urls import reverse

import pytest
import responses

from baserow.core.sso.oidc.handler import SESSION_NONCE_KEY, SESSION_STATE_KEY
from baserow.core.user.exceptions import DisabledSignupError
from baserow.core.user.handler import UserHandler
from baserow.test_utils.oidc import FakeOIDCProvider

User = get_user_model()


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


def _drive_callback(api_client, idp, responses_mock):
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
def test_oidc_creates_user_even_when_signups_disabled(api_client, data_fixture):
    data_fixture.update_settings(allow_new_signups=False)
    idp = FakeOIDCProvider(email="provisioned@example.com", full_name="Provisioned")

    with override_settings(BASEROW_OIDC_PROVIDERS=[idp.config]):
        response = _drive_callback(api_client, idp, responses)

    assert response.status_code == 302
    query = parse_qs(urlparse(response.headers["Location"]).query)
    assert "token" in query
    assert User.objects.filter(email="provisioned@example.com").exists()


@pytest.mark.django_db
def test_password_signup_still_blocked_when_signups_disabled(data_fixture):
    data_fixture.update_settings(allow_new_signups=False)

    # The password / self-service path never passes bypass_signup_toggle.
    with pytest.raises(DisabledSignupError):
        UserHandler().create_user(
            name="Blocked",
            email="blocked@example.com",
            password="password",
        )

    assert not User.objects.filter(email="blocked@example.com").exists()


@pytest.mark.django_db
def test_bypass_flag_provisions_user_when_signups_disabled(data_fixture):
    data_fixture.update_settings(allow_new_signups=False)

    user = UserHandler().create_user(
        name="Bypassed",
        email="bypassed@example.com",
        password=None,
        bypass_signup_toggle=True,
    )

    assert user.email == "bypassed@example.com"
