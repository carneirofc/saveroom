"""
The OpenID Connect authorization-code flow, driven by env-configured providers.

The flow is: discovery (``.well-known/openid-configuration``) → build authorization
URL (with ``state``, ``nonce`` and a PKCE S256 challenge) → verify the returned
``state`` and exchange the code (with the PKCE verifier) for tokens → validate the ID
token (issuer, audience, expiry, subject, signature via JWKS, and nonce) → read the
userinfo endpoint for the email and name, requiring its ``sub`` to match the ID token's
and, unless the provider opts out, a verified email.
"""

import base64
import hashlib
import secrets
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from django.contrib.sessions.backends.base import SessionBase

import jwt
import requests
from jwt.algorithms import RSAAlgorithm
from loguru import logger
from requests_oauthlib import OAuth2Session

from baserow.core.auth_provider.types import UserInfo
from baserow.core.cache import global_cache
from baserow.core.sso.exceptions import (
    AuthFlowError,
    EmailNotVerified,
    InvalidProviderUrl,
)
from baserow.core.sso.oidc.config import OIDCProviderConfig
from baserow.core.sso.oidc.roles import extract_roles

DISCOVERY_TIMEOUT_SECONDS = 30
JWKS_TIMEOUT_SECONDS = 30
WELL_KNOWN_CACHE_TIMEOUT_SECONDS = 3600
JWKS_CACHE_TIMEOUT_SECONDS = 3600
ALLOWED_SIGNING_ALGORITHMS = ["RS256", "RS384", "RS512"]
PKCE_CODE_CHALLENGE_METHOD = "S256"

SESSION_STATE_KEY = "oidc_oauth_state"
SESSION_NONCE_KEY = "oidc_oauth_nonce"
SESSION_CODE_VERIFIER_KEY = "oidc_oauth_code_verifier"
SESSION_REQUEST_DATA_KEY = "oidc_request_data"


@dataclass
class WellKnownUrls:
    authorization_endpoint: str
    token_endpoint: str
    userinfo_endpoint: str
    jwks_uri: str
    issuer: str


def get_well_known_urls(config: OIDCProviderConfig) -> WellKnownUrls:
    """
    Fetches (and caches) the provider's OpenID Connect discovery document.

    :param config: The provider configuration.
    :raises InvalidProviderUrl: When the discovery document cannot be loaded.
    :return: The discovered endpoints.
    """

    cache_key = f"oidc_well_known_{config.name}"

    def _fetch() -> Dict[str, Any]:
        url = f"{config.issuer.rstrip('/')}/.well-known/openid-configuration"
        response = requests.get(url, timeout=DISCOVERY_TIMEOUT_SECONDS)  # nosec B113
        response.raise_for_status()
        return response.json()

    try:
        document = global_cache.get(
            cache_key,
            default=_fetch,
            timeout=WELL_KNOWN_CACHE_TIMEOUT_SECONDS,
        )
        return WellKnownUrls(
            authorization_endpoint=document["authorization_endpoint"],
            token_endpoint=document["token_endpoint"],
            userinfo_endpoint=document["userinfo_endpoint"],
            jwks_uri=document["jwks_uri"],
            issuer=document["issuer"],
        )
    except Exception as exc:
        logger.exception(
            "Failed to load OpenID Connect discovery document for provider "
            f"'{config.name}'."
        )
        raise InvalidProviderUrl() from exc


def create_pkce_code_challenge(code_verifier: str) -> str:
    """Returns the RFC 7636 S256 code challenge for the given verifier."""

    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


class OIDCHandler:
    """Stateless helper driving the OIDC authorization-code flow for a provider."""

    @classmethod
    def _get_oauth_session(
        cls,
        config: OIDCProviderConfig,
        callback_url: str,
        state: Optional[str] = None,
    ) -> OAuth2Session:
        return OAuth2Session(
            config.client_id,
            redirect_uri=callback_url,
            scope=config.scopes,
            state=state,
        )

    @classmethod
    def get_authorization_redirect_url(
        cls,
        config: OIDCProviderConfig,
        callback_url: str,
        session: SessionBase,
        request_data: Dict[str, Any],
    ) -> str:
        """
        Builds the provider authorization URL that starts the login flow and stores the
        ``state``, ``nonce``, PKCE code verifier and original request data in the
        session for the callback.
        """

        well_known = get_well_known_urls(config)
        oauth = cls._get_oauth_session(config, callback_url)
        nonce = secrets.token_urlsafe(32)
        # The verifier is kept in the Django session rather than on the OAuth2Session,
        # because the callback is served by a different request and session instance.
        code_verifier = secrets.token_urlsafe(64)
        authorization_url, state = oauth.authorization_url(
            well_known.authorization_endpoint,
            nonce=nonce,
            code_challenge=create_pkce_code_challenge(code_verifier),
            code_challenge_method=PKCE_CODE_CHALLENGE_METHOD,
        )
        session[SESSION_STATE_KEY] = state
        session[SESSION_NONCE_KEY] = nonce
        session[SESSION_CODE_VERIFIER_KEY] = code_verifier
        session[SESSION_REQUEST_DATA_KEY] = request_data or {}
        return authorization_url

    @classmethod
    def _pop_request_data(cls, session: SessionBase) -> Dict[str, Any]:
        try:
            return session.pop(SESSION_REQUEST_DATA_KEY) or {}
        except KeyError:
            return {}

    @classmethod
    def get_user_info(
        cls,
        config: OIDCProviderConfig,
        callback_url: str,
        code: str,
        returned_state: Optional[str],
        session: SessionBase,
    ) -> Tuple[UserInfo, str, List[str]]:
        """
        Verifies the returned state, exchanges the authorization code for tokens,
        validates the ID token and reads the userinfo endpoint.

        :param config: The provider configuration.
        :param callback_url: The redirect URI registered with the provider.
        :param code: The authorization code returned by the provider.
        :param returned_state: The ``state`` query parameter of the callback.
        :param session: The Django session holding the state / nonce / verifier.
        :raises AuthFlowError: When the flow fails or the ID token is invalid.
        :raises EmailNotVerified: When the provider requires a verified email and the
            identity provider does not vouch for it.
        :return: The user info, the original (relative) url to redirect to, and the
            user's IdP roles.
        """

        well_known = get_well_known_urls(config)
        # Everything is popped up front so a failed attempt can never be replayed.
        state = session.pop(SESSION_STATE_KEY, None)
        nonce = session.pop(SESSION_NONCE_KEY, None)
        code_verifier = session.pop(SESSION_CODE_VERIFIER_KEY, None)
        request_data = cls._pop_request_data(session)

        # Fail closed: `fetch_token(code=...)` does not compare the state itself.
        if (
            not state
            or not returned_state
            or not secrets.compare_digest(state, returned_state)
        ):
            raise AuthFlowError("The callback state is missing or does not match.")

        if not code_verifier:
            raise AuthFlowError("The PKCE code verifier is missing from the session.")

        try:
            oauth = cls._get_oauth_session(config, callback_url, state=state)
            token = oauth.fetch_token(
                well_known.token_endpoint,
                code=code,
                client_secret=config.client_secret,
                code_verifier=code_verifier,
            )
        except Exception as exc:
            logger.exception(
                f"OIDC token exchange failed for provider '{config.name}'."
            )
            raise AuthFlowError() from exc

        if "id_token" not in token:
            raise AuthFlowError("The provider did not return an id_token.")

        claims = cls._validate_id_token(config, well_known, token["id_token"], nonce)

        try:
            userinfo = oauth.get(well_known.userinfo_endpoint).json()
        except Exception as exc:
            logger.exception(
                f"Failed to read the userinfo endpoint for provider '{config.name}'."
            )
            raise AuthFlowError() from exc

        # OIDC Core 5.3.2: the userinfo response must be about the ID token's subject.
        if userinfo.get("sub") != claims["sub"]:
            raise AuthFlowError("The userinfo subject does not match the id_token.")

        email, name = cls._extract_email_and_name(config, userinfo)
        if not email:
            raise AuthFlowError("The provider did not return an email address.")

        email_verified = cls._is_email_verified(claims, userinfo)
        if config.require_verified_email and not email_verified:
            raise EmailNotVerified()

        roles = extract_roles(config, claims, userinfo)

        return (
            UserInfo(
                email=email,
                name=name,
                language=request_data.get("language") or None,
                email_verified=email_verified,
            ),
            request_data.get("original", ""),
            roles,
        )

    @classmethod
    def _is_email_verified(
        cls, claims: Dict[str, Any], userinfo: Dict[str, Any]
    ) -> bool:
        """
        True only when the provider explicitly vouches for the email, preferring the
        userinfo response and falling back to the ID token.
        """

        verified = userinfo.get("email_verified", claims.get("email_verified"))
        return verified is True

    @classmethod
    def _validate_id_token(
        cls,
        config: OIDCProviderConfig,
        well_known: WellKnownUrls,
        id_token: str,
        expected_nonce: Optional[str],
    ) -> Dict[str, Any]:
        """
        Validates the ID token signature, issuer, audience, expiry, subject and nonce.

        :raises AuthFlowError: When any check fails.
        :return: The decoded, verified claims.
        """

        try:
            signing_key = cls._get_signing_key(config, well_known, id_token)
            claims = jwt.decode(
                id_token,
                key=signing_key,
                algorithms=ALLOWED_SIGNING_ALGORITHMS,
                audience=config.client_id,
                issuer=well_known.issuer,
                options={"require": ["exp", "iat", "aud", "iss", "sub"]},
            )
        except Exception as exc:
            logger.exception(
                f"OIDC id_token validation failed for provider '{config.name}'."
            )
            raise AuthFlowError() from exc

        # Fail closed: a missing session nonce (lost/expired session between the
        # authorization request and the callback) must be rejected, not accepted.
        if not expected_nonce or claims.get("nonce") != expected_nonce:
            raise AuthFlowError("The id_token nonce is missing or does not match.")

        return claims

    @classmethod
    def _get_signing_key(
        cls,
        config: OIDCProviderConfig,
        well_known: WellKnownUrls,
        id_token: str,
        retry_on_miss: bool = True,
    ):
        """
        Resolves the JWKS key matching the id_token's ``kid``. The JWKS is cached; on a
        cache miss (e.g. rotated keys) the cache is invalidated and refetched once.
        """

        cache_key = f"oidc_jwks_{well_known.jwks_uri}"

        def _fetch() -> Dict[str, Any]:
            response = requests.get(  # nosec B113
                well_known.jwks_uri, timeout=JWKS_TIMEOUT_SECONDS
            )
            response.raise_for_status()
            return response.json()

        try:
            jwks = global_cache.get(
                cache_key, default=_fetch, timeout=JWKS_CACHE_TIMEOUT_SECONDS
            )
        except Exception as exc:
            logger.exception(f"Failed to load the JWKS for provider '{config.name}'.")
            raise AuthFlowError() from exc

        kid = jwt.get_unverified_header(id_token).get("kid")
        for jwk in jwks.get("keys", []):
            if jwk.get("kid") == kid:
                return RSAAlgorithm.from_jwk(jwk)

        if retry_on_miss:
            # The keys may have rotated since we cached them; refetch once.
            global_cache.invalidate(cache_key)
            return cls._get_signing_key(
                config, well_known, id_token, retry_on_miss=False
            )
        raise AuthFlowError(f"No matching JWKS key for kid '{kid}'.")

    @classmethod
    def _extract_email_and_name(
        cls, config: OIDCProviderConfig, claims: Dict[str, Any]
    ) -> Tuple[Optional[str], str]:
        email = claims.get(config.email_claim)
        name = claims.get(config.name_claim) or ""
        name = name.strip() if isinstance(name, str) else ""
        if not name:
            name = email or ""
        return email, name
