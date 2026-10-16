from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test.utils import override_settings

import pytest

from baserow.core.auth_provider.models import OIDCAuthProviderModel
from baserow.test_utils.oidc import FakeOIDCProvider


def _run(*args):
    out = StringIO()
    call_command("link_oidc_account", *args, stdout=out)
    return out.getvalue()


@pytest.mark.django_db
def test_link_creates_the_anchor_and_links_the_accounts(data_fixture):
    idp = FakeOIDCProvider()
    admin = data_fixture.create_user(email="admin@example.com", is_staff=True)
    other = data_fixture.create_user(email="other@example.com")

    with override_settings(BASEROW_OIDC_PROVIDERS=[idp.config]):
        output = _run(
            "link", idp.name, "--email", "Admin@example.com", "--email", other.email
        )

    provider = OIDCAuthProviderModel.objects.get(name=idp.name)
    assert set(provider.users.all()) == {admin, other}
    assert "Linked 'admin@example.com'" in output


@pytest.mark.django_db
def test_link_from_provider_copies_every_link_after_a_rename(data_fixture):
    idp = FakeOIDCProvider(name="new-name")
    users = [data_fixture.create_user() for _ in range(2)]
    old = OIDCAuthProviderModel.objects.create(name="old-name")
    old.users.add(*users)

    with override_settings(BASEROW_OIDC_PROVIDERS=[idp.config]):
        _run("link", "new-name", "--from-provider", "old-name")

    new = OIDCAuthProviderModel.objects.get(name="new-name")
    assert set(new.users.all()) == set(users)


@pytest.mark.django_db
def test_link_refuses_an_unconfigured_provider(data_fixture):
    user = data_fixture.create_user()

    with override_settings(BASEROW_OIDC_PROVIDERS=[]):
        with pytest.raises(CommandError):
            _run("link", "keycloak", "--email", user.email)

    assert not OIDCAuthProviderModel.objects.exists()


@pytest.mark.django_db
def test_link_refuses_an_unknown_email():
    idp = FakeOIDCProvider()

    with override_settings(BASEROW_OIDC_PROVIDERS=[idp.config]):
        with pytest.raises(CommandError):
            _run("link", idp.name, "--email", "nobody@example.com")


@pytest.mark.django_db
def test_unlink_removes_the_link(data_fixture):
    user = data_fixture.create_user()
    provider = OIDCAuthProviderModel.objects.create(name="keycloak")
    provider.users.add(user)

    _run("unlink", "keycloak", "--email", user.email)

    assert not provider.users.filter(id=user.id).exists()


@pytest.mark.django_db
def test_list_shows_the_linked_providers(data_fixture):
    user = data_fixture.create_user(email="listed@example.com")
    OIDCAuthProviderModel.objects.create(name="keycloak").users.add(user)

    output = _run("list", user.email)

    assert "listed@example.com: openid_connect keycloak" in output


@pytest.mark.django_db
def test_list_reports_an_unlinked_account(data_fixture):
    user = data_fixture.create_user(email="lonely@example.com")

    assert "not linked to any provider" in _run("list", user.email)
