import json

from django.core.exceptions import ImproperlyConfigured

import pytest

from baserow.core.sso.oidc.config import (
    DEFAULT_SCOPES,
    DEFAULT_SESSION_LIFETIME_MINUTES,
    OIDCProviderConfig,
    parse_oidc_providers_env,
)

VALID_PROVIDER = {
    "name": "keycloak",
    "display_name": "Keycloak",
    "issuer": "http://localhost:8080/realms/master",
    "client_id": "baserow",
    "client_secret": "secret",
}


def _env(*providers):
    return json.dumps(list(providers))


def test_empty_env_returns_no_providers():
    assert parse_oidc_providers_env(None) == []
    assert parse_oidc_providers_env("") == []
    assert parse_oidc_providers_env("   ") == []


def test_valid_provider_is_parsed_with_defaults():
    providers = parse_oidc_providers_env(_env(VALID_PROVIDER))

    assert len(providers) == 1
    provider = providers[0]
    assert isinstance(provider, OIDCProviderConfig)
    assert provider.name == "keycloak"
    assert provider.display_name == "Keycloak"
    assert provider.issuer == "http://localhost:8080/realms/master"
    assert provider.client_id == "baserow"
    assert provider.client_secret == "secret"
    assert provider.scopes == DEFAULT_SCOPES
    assert provider.email_claim == "email"
    assert provider.name_claim == "name"


def test_display_name_defaults_to_name():
    provider = dict(VALID_PROVIDER)
    del provider["display_name"]

    providers = parse_oidc_providers_env(_env(provider))

    assert providers[0].display_name == "keycloak"


def test_invalid_json_fails_fast():
    with pytest.raises(ImproperlyConfigured):
        parse_oidc_providers_env("{not json")


def test_non_list_fails_fast():
    with pytest.raises(ImproperlyConfigured):
        parse_oidc_providers_env(json.dumps(VALID_PROVIDER))


@pytest.mark.parametrize("missing", ["name", "issuer", "client_id", "client_secret"])
def test_missing_required_field_fails_fast(missing):
    provider = dict(VALID_PROVIDER)
    del provider[missing]

    with pytest.raises(ImproperlyConfigured):
        parse_oidc_providers_env(_env(provider))


def test_invalid_name_fails_fast():
    provider = dict(VALID_PROVIDER, name="not a slug!")

    with pytest.raises(ImproperlyConfigured):
        parse_oidc_providers_env(_env(provider))


def test_invalid_issuer_fails_fast():
    provider = dict(VALID_PROVIDER, issuer="not-a-url")

    with pytest.raises(ImproperlyConfigured):
        parse_oidc_providers_env(_env(provider))


def test_scopes_must_include_openid():
    provider = dict(VALID_PROVIDER, scopes=["email", "profile"])

    with pytest.raises(ImproperlyConfigured):
        parse_oidc_providers_env(_env(provider))


def test_duplicate_names_fail_fast():
    with pytest.raises(ImproperlyConfigured):
        parse_oidc_providers_env(_env(VALID_PROVIDER, VALID_PROVIDER))


def test_multiple_providers_parsed():
    second = dict(VALID_PROVIDER, name="google", display_name="Google")

    providers = parse_oidc_providers_env(_env(VALID_PROVIDER, second))

    assert [p.name for p in providers] == ["keycloak", "google"]


def test_role_mapping_defaults():
    provider = parse_oidc_providers_env(_env(VALID_PROVIDER))[0]

    # The default claim is Keycloak's own, with the client id substituted in.
    assert provider.roles_claim == "resource_access.baserow.roles"
    assert provider.user_roles == []
    assert provider.staff_roles == []
    assert provider.superuser_roles == []
    assert provider.syncs_global_roles is False
    assert provider.mapped_roles == set()
    assert provider.declares_any_mapping is False


def test_roles_claim_substitutes_the_client_id():
    provider = dict(
        VALID_PROVIDER,
        client_id="my-client",
        roles_claim="resource_access.${client_id}.roles",
    )

    config = parse_oidc_providers_env(_env(provider))[0]

    assert config.roles_claim == "resource_access.my-client.roles"


def test_role_mapping_parsed():
    provider = dict(
        VALID_PROVIDER,
        roles_claim="realm_access.roles",
        staff_roles=["staff", "admins"],
        superuser_roles=["superadmins"],
    )

    config = parse_oidc_providers_env(_env(provider))[0]

    assert config.roles_claim == "realm_access.roles"
    assert config.staff_roles == ["staff", "admins"]
    assert config.superuser_roles == ["superadmins"]
    assert config.syncs_global_roles is True
    assert config.declares_any_mapping is True


def test_user_roles_parsed_and_gate_sign_in():
    provider = dict(VALID_PROVIDER, user_roles=["baserow-user"])

    config = parse_oidc_providers_env(_env(provider))[0]

    assert config.user_roles == ["baserow-user"]
    assert config.syncs_global_roles is False
    assert config.mapped_roles == {"baserow-user"}
    assert config.declares_any_mapping is True


@pytest.mark.parametrize("key", ["user_roles", "staff_roles", "superuser_roles"])
def test_role_lists_must_be_lists_of_strings(key):
    provider = dict(VALID_PROVIDER, **{key: "not-a-list"})

    with pytest.raises(ImproperlyConfigured):
        parse_oidc_providers_env(_env(provider))


def test_roles_claim_must_be_non_empty_string():
    provider = dict(VALID_PROVIDER, roles_claim="")

    with pytest.raises(ImproperlyConfigured):
        parse_oidc_providers_env(_env(provider))


@pytest.mark.parametrize(
    "key,value",
    [
        (
            "workspace_mappings",
            [{"client_role": "team-a", "workspace": 7, "permissions": "MEMBER"}],
        ),
        ("team_mappings", [{"client_role": "team-a", "workspace": 7, "team": "A"}]),
        ("strict_membership", True),
    ],
)
def test_removed_workspace_keys_fail_fast(key, value):
    # Refused rather than ignored, so an operator learns their mappings stopped applying.
    provider = dict(VALID_PROVIDER, **{key: value})

    with pytest.raises(ImproperlyConfigured, match="managed in the app"):
        parse_oidc_providers_env(_env(provider))


@pytest.mark.parametrize(
    "key,replacement",
    [
        ("groups_claim", "roles_claim"),
        ("staff_groups", "staff_roles"),
        ("superuser_groups", "superuser_roles"),
    ],
)
def test_retired_provider_keys_fail_fast(key, replacement):
    # Ignoring one would silently drop the access it used to grant.
    provider = dict(VALID_PROVIDER, **{key: ["a"] if key != "groups_claim" else "a"})

    with pytest.raises(ImproperlyConfigured, match=replacement):
        parse_oidc_providers_env(_env(provider))


def test_require_verified_email_defaults_true_and_parses():
    assert parse_oidc_providers_env(_env(VALID_PROVIDER))[0].require_verified_email

    provider = dict(VALID_PROVIDER, require_verified_email=False)
    assert not parse_oidc_providers_env(_env(provider))[0].require_verified_email


def test_require_verified_email_must_be_boolean():
    provider = dict(VALID_PROVIDER, require_verified_email="false")
    with pytest.raises(ImproperlyConfigured):
        parse_oidc_providers_env(_env(provider))


def test_link_existing_accounts_defaults_false_and_parses():
    assert not parse_oidc_providers_env(_env(VALID_PROVIDER))[0].link_existing_accounts

    provider = dict(VALID_PROVIDER, link_existing_accounts=True)
    assert parse_oidc_providers_env(_env(provider))[0].link_existing_accounts


def test_link_existing_accounts_must_be_boolean():
    provider = dict(VALID_PROVIDER, link_existing_accounts="true")
    with pytest.raises(ImproperlyConfigured):
        parse_oidc_providers_env(_env(provider))


def test_session_lifetime_defaults_and_parses():
    default = parse_oidc_providers_env(_env(VALID_PROVIDER))[0]
    assert default.session_lifetime_minutes == DEFAULT_SESSION_LIFETIME_MINUTES

    provider = dict(VALID_PROVIDER, session_lifetime_minutes=15)
    assert parse_oidc_providers_env(_env(provider))[0].session_lifetime_minutes == 15

    provider = dict(VALID_PROVIDER, session_lifetime_minutes=None)
    assert parse_oidc_providers_env(_env(provider))[0].session_lifetime_minutes is None


@pytest.mark.parametrize("value", [0, -5, True, "60", 1.5])
def test_session_lifetime_must_be_a_positive_integer(value):
    provider = dict(VALID_PROVIDER, session_lifetime_minutes=value)
    with pytest.raises(ImproperlyConfigured):
        parse_oidc_providers_env(_env(provider))
