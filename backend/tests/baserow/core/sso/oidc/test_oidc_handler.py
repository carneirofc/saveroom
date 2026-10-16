from urllib.parse import parse_qs, urlparse

from django.core.cache import cache

import pytest
import responses
from cryptography.hazmat.primitives.asymmetric import rsa

from baserow.core.sso.exceptions import (
    AuthFlowError,
    EmailNotVerified,
    InvalidProviderUrl,
)
from baserow.core.sso.oidc.handler import (
    SESSION_CODE_VERIFIER_KEY,
    SESSION_NONCE_KEY,
    SESSION_STATE_KEY,
    OIDCHandler,
    create_pkce_code_challenge,
    get_well_known_urls,
)
from baserow.test_utils.oidc import FakeOIDCProvider

CALLBACK_URL = "https://baserow.example.com/api/sso/oidc/callback/keycloak/"


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


def _authorize(idp, responses_mock):
    """Runs the authorization step and returns (session, nonce)."""

    responses_mock.add(
        responses_mock.GET, idp.discovery_url, json=idp.discovery_document()
    )
    session = {}
    OIDCHandler.get_authorization_redirect_url(
        idp.config, CALLBACK_URL, session, {"original": "/dashboard"}
    )
    return session, session[SESSION_NONCE_KEY]


@responses.activate
def test_discovery_is_fetched():
    idp = FakeOIDCProvider()
    responses.add(responses.GET, idp.discovery_url, json=idp.discovery_document())

    well_known = get_well_known_urls(idp.config)

    assert well_known.issuer == idp.issuer
    assert well_known.token_endpoint == idp.token_endpoint
    assert well_known.jwks_uri == idp.jwks_uri


@responses.activate
def test_discovery_failure_raises_invalid_provider_url():
    idp = FakeOIDCProvider()
    responses.add(responses.GET, idp.discovery_url, status=500)

    with pytest.raises(InvalidProviderUrl):
        get_well_known_urls(idp.config)


@responses.activate
def test_authorization_url_stores_state_and_nonce():
    idp = FakeOIDCProvider()
    responses.add(responses.GET, idp.discovery_url, json=idp.discovery_document())

    session = {}
    url = OIDCHandler.get_authorization_redirect_url(
        idp.config, CALLBACK_URL, session, {"original": "/x"}
    )

    assert url.startswith(idp.authorization_endpoint)
    assert "nonce=" in url
    assert session[SESSION_STATE_KEY]
    assert session[SESSION_NONCE_KEY]


@responses.activate(assert_all_requests_are_fired=False)
def test_full_flow_returns_user_info():
    idp = FakeOIDCProvider()
    session, nonce = _authorize(idp, responses)
    idp.register_all(responses, nonce=nonce)

    user_info, original, roles = OIDCHandler.get_user_info(
        idp.config, CALLBACK_URL, "the-code", session[SESSION_STATE_KEY], session
    )

    assert user_info.email == "alice@example.com"
    assert user_info.name == "Alice Example"
    assert original == "/dashboard"
    assert roles == []


@responses.activate(assert_all_requests_are_fired=False)
def test_full_flow_returns_the_client_roles():
    idp = FakeOIDCProvider(client_roles=["analysts", "engineering"])
    session, nonce = _authorize(idp, responses)
    idp.register_all(responses, nonce=nonce)

    _, _, roles = OIDCHandler.get_user_info(
        idp.config, CALLBACK_URL, "the-code", session[SESSION_STATE_KEY], session
    )

    assert roles == ["analysts", "engineering"]


@responses.activate(assert_all_requests_are_fired=False)
def test_tampered_signature_is_rejected():
    idp = FakeOIDCProvider()
    session, nonce = _authorize(idp, responses)
    # Sign the id_token with a *different* key than the one published in the JWKS.
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    bad_token = idp.mint_id_token(nonce=nonce, sign_with=other_key)
    idp.register_all(responses, id_token=bad_token)

    with pytest.raises(AuthFlowError):
        OIDCHandler.get_user_info(
            idp.config, CALLBACK_URL, "the-code", session[SESSION_STATE_KEY], session
        )


@responses.activate(assert_all_requests_are_fired=False)
def test_expired_token_is_rejected():
    idp = FakeOIDCProvider()
    session, nonce = _authorize(idp, responses)
    expired = idp.mint_id_token(nonce=nonce, expires_in=-10)
    idp.register_all(responses, id_token=expired)

    with pytest.raises(AuthFlowError):
        OIDCHandler.get_user_info(
            idp.config, CALLBACK_URL, "the-code", session[SESSION_STATE_KEY], session
        )


@responses.activate(assert_all_requests_are_fired=False)
def test_wrong_audience_is_rejected():
    idp = FakeOIDCProvider()
    session, nonce = _authorize(idp, responses)
    wrong_aud = idp.mint_id_token(nonce=nonce, audience="someone-else")
    idp.register_all(responses, id_token=wrong_aud)

    with pytest.raises(AuthFlowError):
        OIDCHandler.get_user_info(
            idp.config, CALLBACK_URL, "the-code", session[SESSION_STATE_KEY], session
        )


@responses.activate(assert_all_requests_are_fired=False)
def test_wrong_issuer_is_rejected():
    idp = FakeOIDCProvider()
    session, nonce = _authorize(idp, responses)
    wrong_iss = idp.mint_id_token(nonce=nonce, issuer="https://evil.example.com")
    idp.register_all(responses, id_token=wrong_iss)

    with pytest.raises(AuthFlowError):
        OIDCHandler.get_user_info(
            idp.config, CALLBACK_URL, "the-code", session[SESSION_STATE_KEY], session
        )


@responses.activate(assert_all_requests_are_fired=False)
def test_nonce_mismatch_is_rejected():
    idp = FakeOIDCProvider()
    session, _ = _authorize(idp, responses)
    mismatched = idp.mint_id_token(nonce="not-the-session-nonce")
    idp.register_all(responses, id_token=mismatched)

    with pytest.raises(AuthFlowError):
        OIDCHandler.get_user_info(
            idp.config, CALLBACK_URL, "the-code", session[SESSION_STATE_KEY], session
        )


@responses.activate(assert_all_requests_are_fired=False)
def test_missing_session_nonce_fails_closed():
    idp = FakeOIDCProvider()
    session, nonce = _authorize(idp, responses)
    # Simulate a lost/expired session: the stored nonce is gone by callback time.
    session.pop(SESSION_NONCE_KEY, None)
    idp.register_all(responses, nonce=nonce)

    with pytest.raises(AuthFlowError):
        OIDCHandler.get_user_info(
            idp.config, CALLBACK_URL, "the-code", session[SESSION_STATE_KEY], session
        )


@responses.activate(assert_all_requests_are_fired=False)
def test_missing_id_token_is_rejected():
    idp = FakeOIDCProvider()
    session, nonce = _authorize(idp, responses)
    responses.add(responses.GET, idp.jwks_uri, json=idp.jwks())
    responses.add(
        responses.POST,
        idp.token_endpoint,
        json={"access_token": "x", "token_type": "Bearer"},
    )

    with pytest.raises(AuthFlowError):
        OIDCHandler.get_user_info(
            idp.config, CALLBACK_URL, "the-code", session[SESSION_STATE_KEY], session
        )


def _get_user_info(idp, session, state=None):
    return OIDCHandler.get_user_info(
        idp.config,
        CALLBACK_URL,
        "the-code",
        session.get(SESSION_STATE_KEY) if state is None else state,
        session,
    )


@responses.activate
def test_authorization_url_carries_a_pkce_s256_challenge():
    idp = FakeOIDCProvider()
    responses.add(responses.GET, idp.discovery_url, json=idp.discovery_document())

    session = {}
    url = OIDCHandler.get_authorization_redirect_url(
        idp.config, CALLBACK_URL, session, {}
    )

    query = parse_qs(urlparse(url).query)
    assert query["code_challenge_method"] == ["S256"]
    assert query["code_challenge"] == [
        create_pkce_code_challenge(session[SESSION_CODE_VERIFIER_KEY])
    ]


@responses.activate(assert_all_requests_are_fired=False)
def test_code_verifier_is_sent_to_the_token_endpoint():
    idp = FakeOIDCProvider()
    session, nonce = _authorize(idp, responses)
    verifier = session[SESSION_CODE_VERIFIER_KEY]
    idp.register_all(responses, nonce=nonce)

    _get_user_info(idp, session)

    token_call = next(
        call for call in responses.calls if call.request.url == idp.token_endpoint
    )
    assert parse_qs(token_call.request.body)["code_verifier"] == [verifier]


@responses.activate(assert_all_requests_are_fired=False)
def test_missing_code_verifier_fails_closed():
    idp = FakeOIDCProvider()
    session, nonce = _authorize(idp, responses)
    session.pop(SESSION_CODE_VERIFIER_KEY)
    idp.register_all(responses, nonce=nonce)

    with pytest.raises(AuthFlowError):
        _get_user_info(idp, session)


@responses.activate(assert_all_requests_are_fired=False)
def test_state_mismatch_is_rejected():
    idp = FakeOIDCProvider()
    session, nonce = _authorize(idp, responses)
    idp.register_all(responses, nonce=nonce)

    with pytest.raises(AuthFlowError):
        _get_user_info(idp, session, state="not-the-session-state")


@responses.activate(assert_all_requests_are_fired=False)
def test_missing_returned_state_is_rejected():
    idp = FakeOIDCProvider()
    session, nonce = _authorize(idp, responses)
    idp.register_all(responses, nonce=nonce)

    with pytest.raises(AuthFlowError):
        _get_user_info(idp, session, state="")


@responses.activate(assert_all_requests_are_fired=False)
def test_missing_session_state_fails_closed():
    idp = FakeOIDCProvider()
    session, nonce = _authorize(idp, responses)
    state = session.pop(SESSION_STATE_KEY)
    idp.register_all(responses, nonce=nonce)

    with pytest.raises(AuthFlowError):
        _get_user_info(idp, session, state=state)


@responses.activate(assert_all_requests_are_fired=False)
def test_userinfo_subject_mismatch_is_rejected():
    idp = FakeOIDCProvider()
    session, nonce = _authorize(idp, responses)
    idp.register_all(responses, nonce=nonce, userinfo_extra={"sub": "someone-else"})

    with pytest.raises(AuthFlowError):
        _get_user_info(idp, session)


@pytest.mark.parametrize("email_verified", [False, None, "true"])
@responses.activate(assert_all_requests_are_fired=False)
def test_unverified_email_is_rejected(email_verified):
    idp = FakeOIDCProvider()
    session, nonce = _authorize(idp, responses)
    idp.register_all(
        responses, nonce=nonce, userinfo_extra={"email_verified": email_verified}
    )

    with pytest.raises(EmailNotVerified):
        _get_user_info(idp, session)


@responses.activate(assert_all_requests_are_fired=False)
def test_email_verified_falls_back_to_the_id_token():
    idp = FakeOIDCProvider()
    session, nonce = _authorize(idp, responses)
    id_token = idp.mint_id_token(nonce=nonce, extra_claims={"email_verified": True})
    idp.register_all(responses, id_token=id_token)
    # Drop the claim from userinfo so only the ID token vouches for the email.
    responses.replace(
        responses.GET,
        idp.userinfo_endpoint,
        json={k: v for k, v in idp.userinfo().items() if k != "email_verified"},
    )

    user_info, _, _ = _get_user_info(idp, session)

    assert user_info.email == "alice@example.com"


@responses.activate(assert_all_requests_are_fired=False)
def test_unverified_email_is_accepted_when_the_provider_opts_out():
    idp = FakeOIDCProvider(require_verified_email=False)
    session, nonce = _authorize(idp, responses)
    idp.register_all(responses, nonce=nonce, userinfo_extra={"email_verified": False})

    user_info, _, _ = _get_user_info(idp, session)

    assert user_info.email == "alice@example.com"
