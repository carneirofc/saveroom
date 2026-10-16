import dataclasses

import pytest

from baserow.core.sso.exceptions import NoMappedRole
from baserow.core.sso.oidc.config import OIDCProviderConfig
from baserow.core.sso.oidc.roles import (
    enforce_role_access,
    extract_roles,
    resolve_claim,
    split_claim_path,
    sync_global_roles,
)

BASE_CONFIG = OIDCProviderConfig(
    name="rhbk",
    display_name="Keycloak",
    issuer="https://idp.example.com/realms/test",
    client_id="baserow",
    client_secret="secret",
    roles_claim="resource_access.baserow.roles",
)


def _config(**overrides):
    return dataclasses.replace(BASE_CONFIG, **overrides)


def _client_roles(*roles):
    """Builds the claim shape Keycloak emits for a client's roles."""

    return {"resource_access": {"baserow": {"roles": list(roles)}}}


# --- claim path resolution ------------------------------------------------


def test_split_claim_path_splits_on_dots():
    assert split_claim_path("resource_access.baserow.roles") == [
        "resource_access",
        "baserow",
        "roles",
    ]


def test_split_claim_path_honours_escaped_dots():
    assert split_claim_path(r"resource_access\.baserow\.roles") == [
        "resource_access.baserow.roles"
    ]


def test_resolve_claim_walks_a_nested_path():
    assert resolve_claim(_client_roles("a", "b"), "resource_access.baserow.roles") == [
        "a",
        "b",
    ]


def test_resolve_claim_falls_back_to_a_flat_key():
    # A mapper that emits the claim un-nested, under a name containing literal dots.
    source = {"resource_access.baserow.roles": ["a"]}
    assert resolve_claim(source, "resource_access.baserow.roles") == ["a"]


def test_resolve_claim_reads_an_escaped_flat_key():
    source = {"resource_access.baserow.roles": ["a"]}
    assert resolve_claim(source, r"resource_access\.baserow\.roles") == ["a"]


def test_resolve_claim_reads_realm_roles():
    source = {"realm_access": {"roles": ["realm-admin"]}}
    assert resolve_claim(source, "realm_access.roles") == ["realm-admin"]


def test_resolve_claim_supports_a_string_value():
    assert resolve_claim({"roles": "solo"}, "roles") == ["solo"]


def test_resolve_claim_empty_when_absent():
    assert resolve_claim({}, "resource_access.baserow.roles") == []


def test_resolve_claim_empty_when_partially_resolved():
    # The client has no roles entry, so the walk stops half way.
    assert (
        resolve_claim(
            {"resource_access": {"other": {"roles": ["a"]}}},
            "resource_access.baserow.roles",
        )
        == []
    )


def test_resolve_claim_empty_when_not_a_string_list():
    assert resolve_claim({"roles": {"nested": True}}, "roles") == []


# --- extract_roles --------------------------------------------------------


def test_extract_roles_from_id_token():
    assert extract_roles(BASE_CONFIG, _client_roles("a", "b"), {}) == ["a", "b"]


def test_extract_roles_from_userinfo():
    assert extract_roles(BASE_CONFIG, {}, _client_roles("c")) == ["c"]


def test_extract_roles_unions_both_sources():
    roles = extract_roles(BASE_CONFIG, _client_roles("a"), _client_roles("a", "b"))
    assert roles == ["a", "b"]


def test_extract_roles_custom_claim_name():
    config = _config(roles_claim="realm_access.roles")
    assert extract_roles(config, {"realm_access": {"roles": ["x"]}}, {}) == ["x"]


def test_extract_roles_empty_when_absent():
    assert extract_roles(BASE_CONFIG, {}, {}) == []


# --- enforce_role_access --------------------------------------------------


def test_access_is_not_gated_when_no_role_is_mapped():
    # A provider that maps nothing is a plain sign-in provider.
    enforce_role_access(BASE_CONFIG, [])


def test_access_granted_by_a_staff_role():
    enforce_role_access(_config(staff_roles=["ops"]), ["ops"])


def test_access_granted_by_a_superuser_role():
    enforce_role_access(_config(superuser_roles=["admins"]), ["admins"])


def test_access_granted_by_a_user_role():
    enforce_role_access(_config(user_roles=["baserow-user"]), ["baserow-user"])


def test_access_refused_without_a_mapped_role():
    config = _config(staff_roles=["ops"], user_roles=["baserow-user"])
    with pytest.raises(NoMappedRole):
        enforce_role_access(config, ["something-else"])


def test_access_refused_without_any_role():
    with pytest.raises(NoMappedRole):
        enforce_role_access(_config(staff_roles=["ops"]), [])


# --- sync_global_roles ----------------------------------------------------


@pytest.mark.django_db
def test_staff_role_grants_staff(data_fixture):
    user = data_fixture.create_user()
    assert user.is_staff is False

    sync_global_roles(user, ["staff"], _config(staff_roles=["staff"]))

    user.refresh_from_db()
    assert user.is_staff is True


@pytest.mark.django_db
def test_losing_the_staff_role_revokes_staff(data_fixture):
    user = data_fixture.create_user()
    user.is_staff = True
    user.save()

    sync_global_roles(user, ["other"], _config(staff_roles=["staff"]))

    user.refresh_from_db()
    assert user.is_staff is False


@pytest.mark.django_db
def test_superuser_role_grants_superuser_and_staff(data_fixture):
    user = data_fixture.create_user()

    sync_global_roles(user, ["admins"], _config(superuser_roles=["admins"]))

    user.refresh_from_db()
    assert user.is_superuser is True
    assert user.is_staff is True


@pytest.mark.django_db
def test_losing_the_superuser_role_revokes_superuser(data_fixture):
    user = data_fixture.create_user()
    user.is_superuser = True
    user.is_staff = True
    user.save()

    sync_global_roles(
        user, [], _config(superuser_roles=["admins"], staff_roles=["staff"])
    )

    user.refresh_from_db()
    assert user.is_superuser is False
    assert user.is_staff is False


@pytest.mark.django_db
def test_local_admin_untouched_when_provider_maps_no_roles(data_fixture):
    # Represents the break-glass admin: the provider configures no role mappings,
    # so a local admin's flags are never reconciled.
    user = data_fixture.create_user()
    user.is_staff = True
    user.is_superuser = True
    user.save()

    sync_global_roles(user, [], BASE_CONFIG)

    user.refresh_from_db()
    assert user.is_staff is True
    assert user.is_superuser is True


@pytest.mark.django_db
def test_only_configured_dimension_is_reconciled(data_fixture):
    # staff_roles configured but superuser_roles not: is_superuser must be left
    # alone even though the user holds no staff role.
    user = data_fixture.create_user()
    user.is_superuser = True
    user.is_staff = True
    user.save()

    sync_global_roles(user, [], _config(staff_roles=["staff"]))

    user.refresh_from_db()
    # is_superuser untouched (not mapped); is_staff kept True because superuser
    # implies staff.
    assert user.is_superuser is True
    assert user.is_staff is True
