"""
Shared single-sign-on helpers.

These are re-homed from the (removed) enterprise SSO module into core so that the
FOSS OIDC login can reuse them. The license gate that used to guard SSO is gone: in
this fork SSO is always available.
"""

from datetime import timedelta
from enum import Enum
from functools import wraps
from typing import Callable, Dict, Optional, Type
from urllib.parse import urljoin, urlparse

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.http import HttpResponse
from django.shortcuts import redirect

from requests.models import PreparedRequest

from baserow.core.user.utils import generate_session_tokens_for_user, sign_user_session


# Keep these in sync with the `loginError` locale keys in the web-frontend
# (web-frontend/modules/core/locales/en.json).
class SsoErrorCode(Enum):
    USER_DEACTIVATED = "errorUserDeactivated"
    PROVIDER_DOES_NOT_EXIST = "errorProviderDoesNotExist"
    AUTH_FLOW_ERROR = "errorAuthFlowError"
    DIFFERENT_PROVIDER = "errorDifferentProvider"
    SIGNUP_DISABLED = "errorSignupDisabled"
    NO_MAPPED_ROLE = "errorNoMappedRole"
    EMAIL_NOT_VERIFIED = "errorEmailNotVerified"


class map_sso_exceptions:
    """
    A view decorator that maps exceptions to SSO error codes. If the decorated view
    raises an exception present in the mapping, the ``on_error`` handler is called with
    the mapped error code (by default redirecting to the frontend error page) and its
    response is returned. Unmapped exceptions propagate normally.
    """

    def __init__(
        self,
        mapping: Dict[Type[Exception], SsoErrorCode],
        on_error: Optional[Callable[[SsoErrorCode], HttpResponse]] = None,
    ):
        self.mapping = mapping
        self.on_error = on_error or redirect_to_sign_in_error_page

    def __call__(self, func):
        @wraps(func)
        def wrapped_function(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as exc:
                for exception, error_code in self.mapping.items():
                    if isinstance(exc, exception):
                        return self.on_error(error_code)
                raise

        return wrapped_function


def urlencode_query_params(url: str, query_params: Dict[str, str]) -> str:
    """Adds the given query parameters to the url."""

    req = PreparedRequest()
    req.prepare_url(url, query_params)
    return req.url


def get_frontend_default_redirect_url() -> str:
    return urljoin(settings.PUBLIC_WEB_FRONTEND_URL, "/dashboard")


def get_frontend_login_error_url() -> str:
    return urljoin(settings.PUBLIC_WEB_FRONTEND_URL, "/login")


def redirect_to_sign_in_error_page(
    error_code: Optional[SsoErrorCode] = None,
) -> HttpResponse:
    """Redirects the user to the frontend login error page with the error code."""

    frontend_error_page_url = get_frontend_login_error_url()
    if error_code:
        frontend_error_page_url = urlencode_query_params(
            frontend_error_page_url, {"error": error_code.value}
        )
    return redirect(frontend_error_page_url)


def get_valid_frontend_url(requested_original_url: Optional[str] = None) -> str:
    """
    Returns a valid absolute frontend url based on the original (relative) url the
    user requested before being redirected to the login. Falls back to the dashboard
    when the requested url is empty or points to a different host.
    """

    default_url = get_frontend_default_redirect_url()
    default_parsed = urlparse(default_url)
    requested_parsed = urlparse(requested_original_url or "")

    if requested_parsed.hostname is None:
        # Relative url: prefix it with the frontend host.
        requested_parsed = default_parsed._replace(path=requested_parsed.path)
    elif requested_parsed.hostname != default_parsed.hostname:
        # Absolute url pointing elsewhere: reset to the default.
        requested_parsed = default_parsed

    if requested_parsed.path in ("", "/"):
        requested_parsed = requested_parsed._replace(path=default_parsed.path)

    return requested_parsed.geturl()


def urlencode_user_tokens(
    frontend_url: str,
    user: AbstractUser,
    refresh_lifetime: Optional[timedelta] = None,
) -> str:
    """
    Adds a fresh refresh token and signed user session as query parameters to the
    frontend url so the SPA can start an authenticated session.

    :param refresh_lifetime: Optionally bounds the session to this lifetime instead of
        the global `REFRESH_TOKEN_LIFETIME`.
    """

    user_tokens = generate_session_tokens_for_user(
        user, include_refresh_token=True, refresh_lifetime=refresh_lifetime
    )
    refresh_token = user_tokens["refresh_token"]
    user_session = sign_user_session(user.id, refresh_token)
    return urlencode_query_params(
        frontend_url,
        {"token": refresh_token, "user_session": user_session},
    )


def redirect_user_on_success(
    user: AbstractUser,
    requested_original_url: Optional[str] = None,
    refresh_lifetime: Optional[timedelta] = None,
) -> HttpResponse:
    """
    Redirects the freshly authenticated user to a valid frontend url, embedding the
    JWT refresh token so the SPA can start a new session.

    :param refresh_lifetime: Optionally bounds the session to this lifetime instead of
        the global `REFRESH_TOKEN_LIFETIME`.
    """

    valid_frontend_url = get_valid_frontend_url(requested_original_url)
    redirect_url = urlencode_user_tokens(valid_frontend_url, user, refresh_lifetime)
    return redirect(redirect_url)
