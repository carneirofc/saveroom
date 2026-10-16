"""
Parsing and validation of the env-configured OIDC providers.

Providers are declared entirely through the ``BASEROW_OIDC_PROVIDERS`` environment
variable as a JSON list. The configuration is the source of truth; a lightweight
database row (see ``OIDCAuthProviderModel``) is upserted per provider only to anchor
the user linkage that the shared auth-provider machinery relies on.

The IdP only defines global profiles, expressed as client roles: who may sign in
(``user_roles``), who is staff and who is superuser. Workspace membership, teams and
database/table access are managed in the app. A provider that maps any client role
refuses users carrying none of them.

The env var is parsed and structurally validated once, at startup, so that an invalid
configuration fails fast with a clear error instead of surfacing at login time. Network
reachable checks (OIDC discovery) are intentionally deferred to login time.

IMPORTANT: this module is imported from ``config/settings/base.py`` while Django
settings are still being evaluated (before the app registry is ready). Keep it
import-light — stdlib and ``django.core.exceptions`` only — and never import Django
models or ``requests_oauthlib`` here, or settings evaluation will break.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlparse

from django.core.exceptions import ImproperlyConfigured

DEFAULT_SCOPES = ["openid", "email", "profile"]

# Keycloak/RHBK nests a client's roles under this claim, substituting the client id.
# Matching their built-in mapper's default lets an operator paste the claim name in.
DEFAULT_ROLES_CLAIM = "resource_access.${client_id}.roles"
CLIENT_ID_PLACEHOLDER = "${client_id}"

# A working day: client roles removed in the IdP stop applying within this window, since
# the user has to sign in again (and be re-synced) once the session ends.
DEFAULT_SESSION_LIFETIME_MINUTES = 8 * 60

# Config keys retired by the move to client roles, mapped to their replacement. They are
# refused rather than ignored: silently dropping `staff_groups` would revoke every admin.
RETIRED_PROVIDER_KEYS = {
    "groups_claim": "roles_claim",
    "staff_groups": "staff_roles",
    "superuser_groups": "superuser_roles",
}

# Workspace-scoped keys removed because workspaces are managed in the app. Refused so an
# operator upgrading learns their mappings no longer apply instead of silently losing
# the memberships they granted.
REMOVED_PROVIDER_KEYS = ("workspace_mappings", "team_mappings", "strict_membership")

# A provider name is used in URLs and as the database anchor key, so keep it to a
# conservative, url-safe slug.
_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


@dataclass(frozen=True)
class OIDCProviderConfig:
    """A single env-declared OIDC provider."""

    name: str
    display_name: str
    issuer: str
    client_id: str
    client_secret: str
    scopes: List[str] = field(default_factory=lambda: list(DEFAULT_SCOPES))
    # The claim (in the ID token / userinfo) that holds the user's email.
    email_claim: str = "email"
    # The claim that holds the user's display name.
    name_claim: str = "name"
    # The (possibly dotted) claim path that holds the user's IdP roles.
    roles_claim: str = DEFAULT_ROLES_CLAIM
    # IdP client roles whose holders may sign in as regular users. They get an account
    # but no workspace access until a workspace admin adds them in the app.
    user_roles: List[str] = field(default_factory=list)
    # IdP client roles whose holders are granted Baserow global staff.
    staff_roles: List[str] = field(default_factory=list)
    # IdP client roles whose holders are granted Baserow global superuser.
    superuser_roles: List[str] = field(default_factory=list)
    # When True, a user whose `email_verified` claim is not true is refused, since the
    # email is what links the identity to a Baserow account.
    require_verified_email: bool = True
    # When True, an existing non-staff account whose email the IdP explicitly verifies
    # is linked to this provider on first sign-in instead of being refused as belonging
    # to a different authentication provider.
    link_existing_accounts: bool = False
    # How long a session started through this provider lasts before the user has to
    # sign in again, which is also when their client roles are re-synced. None falls
    # back to the global `REFRESH_TOKEN_LIFETIME`.
    session_lifetime_minutes: Optional[int] = DEFAULT_SESSION_LIFETIME_MINUTES

    @property
    def syncs_global_roles(self) -> bool:
        """True when this provider maps any IdP client role to a global role."""

        return bool(self.staff_roles) or bool(self.superuser_roles)

    @property
    def mapped_roles(self) -> Set[str]:
        """Every IdP client role that lets its holder sign in."""

        return set(self.user_roles) | set(self.staff_roles) | set(self.superuser_roles)

    @property
    def declares_any_mapping(self) -> bool:
        """
        True when this provider derives any access from client roles, and a user
        carrying none of them must therefore be refused.
        """

        return bool(self.mapped_roles)


def _require_str(provider: Dict[str, Any], key: str, index: int) -> str:
    value = provider.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ImproperlyConfigured(
            f"BASEROW_OIDC_PROVIDERS[{index}]: '{key}' is required and must be a "
            f"non-empty string."
        )
    return value.strip()


def _string_list(provider: Dict[str, Any], key: str, index: int) -> List[str]:
    """Validates an optional list-of-strings provider field, defaulting to []."""

    value = provider.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ImproperlyConfigured(
            f"BASEROW_OIDC_PROVIDERS[{index}]: '{key}' must be a list of strings."
        )
    return value


def _reject_retired_keys(provider: Dict[str, Any], index: int) -> None:
    """
    Fails fast on keys from older configuration formats.

    Ignoring one would silently drop the access it used to grant, so an operator
    upgrading is told exactly what changed.
    """

    prefix = f"BASEROW_OIDC_PROVIDERS[{index}]"
    for old_key, new_key in RETIRED_PROVIDER_KEYS.items():
        if old_key in provider:
            raise ImproperlyConfigured(
                f"{prefix}: '{old_key}' is no longer supported; access is now derived "
                f"from IdP client roles. Rename it to '{new_key}'."
            )
    for removed_key in REMOVED_PROVIDER_KEYS:
        if removed_key in provider:
            raise ImproperlyConfigured(
                f"{prefix}: '{removed_key}' is no longer supported. The IdP only "
                f"defines who may sign in ('user_roles') and who is staff or "
                f"superuser; workspace members, teams and access are managed in the "
                f"app. Remove '{removed_key}' and add members to workspaces in the app."
            )


def _validate_provider(provider: Any, index: int) -> OIDCProviderConfig:
    if not isinstance(provider, dict):
        raise ImproperlyConfigured(
            f"BASEROW_OIDC_PROVIDERS[{index}]: each provider must be a JSON object."
        )

    _reject_retired_keys(provider, index)

    name = _require_str(provider, "name", index)
    if not _NAME_RE.match(name):
        raise ImproperlyConfigured(
            f"BASEROW_OIDC_PROVIDERS[{index}]: 'name' ('{name}') may only contain "
            f"letters, digits, hyphens and underscores."
        )

    issuer = _require_str(provider, "issuer", index)
    parsed_issuer = urlparse(issuer)
    if parsed_issuer.scheme not in ("http", "https") or not parsed_issuer.netloc:
        raise ImproperlyConfigured(
            f"BASEROW_OIDC_PROVIDERS[{index}]: 'issuer' must be a valid http(s) URL."
        )

    client_id = _require_str(provider, "client_id", index)
    client_secret = _require_str(provider, "client_secret", index)

    display_name = provider.get("display_name") or name
    if not isinstance(display_name, str) or not display_name.strip():
        raise ImproperlyConfigured(
            f"BASEROW_OIDC_PROVIDERS[{index}]: 'display_name' must be a non-empty "
            f"string when provided."
        )

    scopes = provider.get("scopes", list(DEFAULT_SCOPES))
    if not isinstance(scopes, list) or not all(isinstance(s, str) for s in scopes):
        raise ImproperlyConfigured(
            f"BASEROW_OIDC_PROVIDERS[{index}]: 'scopes' must be a list of strings."
        )
    if "openid" not in scopes:
        raise ImproperlyConfigured(
            f"BASEROW_OIDC_PROVIDERS[{index}]: 'scopes' must include 'openid'."
        )

    email_claim = provider.get("email_claim", "email")
    name_claim = provider.get("name_claim", "name")
    roles_claim = provider.get("roles_claim", DEFAULT_ROLES_CLAIM)
    for claim_key, claim_value in (
        ("email_claim", email_claim),
        ("name_claim", name_claim),
        ("roles_claim", roles_claim),
    ):
        if not isinstance(claim_value, str) or not claim_value.strip():
            raise ImproperlyConfigured(
                f"BASEROW_OIDC_PROVIDERS[{index}]: '{claim_key}' must be a non-empty "
                f"string."
            )

    # Keycloak writes its mapper claim names with a `${client_id}` placeholder, so the
    # operator can paste one in verbatim.
    roles_claim = roles_claim.strip().replace(CLIENT_ID_PLACEHOLDER, client_id)

    user_roles = _string_list(provider, "user_roles", index)
    staff_roles = _string_list(provider, "staff_roles", index)
    superuser_roles = _string_list(provider, "superuser_roles", index)

    require_verified_email = provider.get("require_verified_email", True)
    if not isinstance(require_verified_email, bool):
        raise ImproperlyConfigured(
            f"BASEROW_OIDC_PROVIDERS[{index}]: 'require_verified_email' must be a "
            f"boolean."
        )

    link_existing_accounts = provider.get("link_existing_accounts", False)
    if not isinstance(link_existing_accounts, bool):
        raise ImproperlyConfigured(
            f"BASEROW_OIDC_PROVIDERS[{index}]: 'link_existing_accounts' must be a "
            f"boolean."
        )

    session_lifetime_minutes = provider.get(
        "session_lifetime_minutes", DEFAULT_SESSION_LIFETIME_MINUTES
    )
    # bool is a subclass of int; reject it explicitly.
    if session_lifetime_minutes is not None and (
        not isinstance(session_lifetime_minutes, int)
        or isinstance(session_lifetime_minutes, bool)
        or session_lifetime_minutes <= 0
    ):
        raise ImproperlyConfigured(
            f"BASEROW_OIDC_PROVIDERS[{index}]: 'session_lifetime_minutes' must be a "
            f"positive integer, or null to use the global refresh token lifetime."
        )

    return OIDCProviderConfig(
        name=name,
        display_name=display_name.strip(),
        issuer=issuer,
        client_id=client_id,
        client_secret=client_secret,
        scopes=scopes,
        email_claim=email_claim.strip(),
        name_claim=name_claim.strip(),
        roles_claim=roles_claim,
        user_roles=user_roles,
        staff_roles=staff_roles,
        superuser_roles=superuser_roles,
        require_verified_email=require_verified_email,
        link_existing_accounts=link_existing_accounts,
        session_lifetime_minutes=session_lifetime_minutes,
    )


def parse_oidc_providers_env(raw: Optional[str]) -> List[OIDCProviderConfig]:
    """
    Parses and validates the ``BASEROW_OIDC_PROVIDERS`` environment value.

    :param raw: The raw JSON string (or None / empty when unset).
    :raises ImproperlyConfigured: When the JSON is invalid or a provider is malformed.
    :return: The list of validated provider configs (possibly empty).
    """

    if raw is None or not raw.strip():
        return []

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ImproperlyConfigured(
            f"BASEROW_OIDC_PROVIDERS is not valid JSON: {exc}."
        ) from exc

    if not isinstance(data, list):
        raise ImproperlyConfigured(
            "BASEROW_OIDC_PROVIDERS must be a JSON list of provider objects."
        )

    providers: List[OIDCProviderConfig] = []
    seen_names = set()
    for index, provider in enumerate(data):
        config = _validate_provider(provider, index)
        if config.name in seen_names:
            raise ImproperlyConfigured(
                f"BASEROW_OIDC_PROVIDERS: duplicate provider name '{config.name}'."
            )
        seen_names.add(config.name)
        providers.append(config)

    return providers


def get_oidc_providers() -> List[OIDCProviderConfig]:
    """Returns the configured OIDC providers from settings."""

    from django.conf import settings

    return list(getattr(settings, "BASEROW_OIDC_PROVIDERS", []))


def get_oidc_provider(name: str) -> Optional[OIDCProviderConfig]:
    """Returns the configured OIDC provider with the given name, or None."""

    for provider in get_oidc_providers():
        if provider.name == name:
            return provider
    return None
