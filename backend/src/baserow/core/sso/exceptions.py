class SsoError(Exception):
    """Base class for single-sign-on errors."""


class AuthFlowError(SsoError):
    """
    Raised when the SSO authentication flow fails, e.g. because the identity
    provider is unavailable, misconfigured, or returned an invalid response.
    """


class InvalidProviderUrl(SsoError):
    """Raised when the identity provider's discovery document cannot be loaded."""


class OIDCProviderNotFound(SsoError):
    """Raised when no env-configured OIDC provider matches the requested name."""


class EmailNotVerified(SsoError):
    """
    Raised when the identity provider does not vouch for the user's email address, so
    it must not be used to find or provision a Baserow account.
    """


class NoMappedRole(SsoError):
    """
    Raised when the identity provider derives access from client roles but the user
    carries none of the mapped ones, so they must not be signed in or provisioned.
    """
