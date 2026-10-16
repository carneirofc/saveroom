"""
Reading Keycloak/RHBK client roles out of the OIDC claims, and mapping them to access.

All access is driven by the roles found under the provider's ``roles_claim``. Keycloak
nests client roles under ``resource_access.<client_id>.roles`` and realm roles under
``realm_access.roles``, so the claim is addressed by a dotted path rather than a flat
key. A literal dot inside a claim name is escaped as ``\\.``, following Keycloak's own
convention for mappers that emit an un-nested claim.

Roles are reconciled on every login: a user in a mapped staff/superuser role is granted
the role, and a user who no longer carries it has it revoked. Because this only runs
during an OIDC login, a local break-glass admin (who never logs in via OIDC) is never
touched.
"""

import re
from typing import Any, Dict, List, Sequence

from django.contrib.auth.models import AbstractUser

from baserow.core.sso.exceptions import NoMappedRole
from baserow.core.sso.oidc.config import OIDCProviderConfig

# Splits a claim path on dots that are not escaped with a backslash.
_UNESCAPED_DOT_RE = re.compile(r"(?<!\\)\.")


def split_claim_path(path: str) -> List[str]:
    """
    Splits a dotted claim path into its segments, honouring ``\\.`` as a literal dot.

    :param path: The claim path, e.g. ``resource_access.baserow.roles``.
    :return: The path segments, with their escapes removed.
    """

    return [segment.replace("\\.", ".") for segment in _UNESCAPED_DOT_RE.split(path)]


def resolve_claim(source: Dict[str, Any], path: str) -> List[str]:
    """
    Resolves a (possibly nested) claim into a list of string values.

    The path is walked segment by segment. When the walk does not resolve, the whole
    path is retried as a flat key, so a mapper configured to emit a literal
    ``"resource_access.baserow.roles"`` claim works without escaping the dots.

    :param source: The decoded claims to read from.
    :param path: The claim path to resolve.
    :return: The claim's values, or an empty list when it is absent or not a
        string / list of strings.
    """

    value: Any = source
    for segment in split_claim_path(path):
        if not isinstance(value, dict) or segment not in value:
            value = source.get(path)
            break
        value = value[segment]

    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str) and value:
        return [value]
    return []


def extract_roles(
    config: OIDCProviderConfig,
    id_token_claims: Dict[str, Any],
    userinfo: Dict[str, Any],
) -> List[str]:
    """
    Returns the union of the roles found under the configured roles claim in both the
    ID token and the userinfo response.
    """

    roles = set()
    for claims in (id_token_claims, userinfo):
        roles.update(resolve_claim(claims, config.roles_claim))
    return sorted(roles)


def enforce_role_access(config: OIDCProviderConfig, roles: Sequence[str]) -> None:
    """
    Refuses the login when the provider maps roles to access but the user carries none
    of them.

    A provider that declares no mapping at all is not gated, so it keeps working as a
    plain sign-in provider.

    :param config: The provider configuration holding the role mappings.
    :param roles: The user's current IdP roles.
    :raises NoMappedRole: When the user matches none of the mapped roles.
    """

    if not config.declares_any_mapping:
        return

    if not set(roles).intersection(config.mapped_roles):
        raise NoMappedRole()


def sync_global_roles(
    user: AbstractUser, roles: List[str], config: OIDCProviderConfig
) -> None:
    """
    Reconciles ``is_staff`` / ``is_superuser`` from the user's current roles.

    Only the dimensions the provider actually maps are reconciled: an instance that
    configures no staff/superuser roles leaves both flags untouched. A superuser is
    also kept as staff so they retain admin access.
    """

    if not config.syncs_global_roles:
        return

    role_set = set(roles)
    changed_fields = []

    is_superuser = user.is_superuser
    if config.superuser_roles:
        is_superuser = bool(role_set.intersection(config.superuser_roles))
        if is_superuser != user.is_superuser:
            user.is_superuser = is_superuser
            changed_fields.append("is_superuser")

    if config.staff_roles:
        is_staff = bool(role_set.intersection(config.staff_roles))
        # Superuser implies staff so admin access is retained.
        is_staff = is_staff or is_superuser
        if is_staff != user.is_staff:
            user.is_staff = is_staff
            changed_fields.append("is_staff")
    elif is_superuser and not user.is_staff:
        user.is_staff = True
        changed_fields.append("is_staff")

    if changed_fields:
        user.save(update_fields=changed_fields)
