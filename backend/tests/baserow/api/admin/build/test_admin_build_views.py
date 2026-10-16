from django.shortcuts import reverse
from django.test.utils import override_settings

import pytest
from rest_framework.status import HTTP_200_OK, HTTP_401_UNAUTHORIZED, HTTP_403_FORBIDDEN

from baserow.version import VERSION


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_admin_build_info_requires_staff(api_client, data_fixture):
    normal_user = data_fixture.create_user(is_staff=False)
    normal_token = data_fixture.generate_token(user=normal_user)

    response = api_client.get(
        reverse("api:admin:build:build"),
        format="json",
        HTTP_AUTHORIZATION=f"JWT {normal_token}",
    )
    assert response.status_code == HTTP_403_FORBIDDEN


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_admin_build_info_requires_authentication(api_client):
    response = api_client.get(reverse("api:admin:build:build"), format="json")
    assert response.status_code == HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
@override_settings(
    DEBUG=True,
    BASEROW_BUILD_VERSION="v0.13.0",
    BASEROW_BUILD_COMMIT="8b38f7dc832a689794023a21ee21e01772ec28de",
    BASEROW_BUILD_DATE="2026-09-18T10:34:30Z",
)
def test_admin_build_info_reports_the_injected_build(api_client, data_fixture):
    admin_user = data_fixture.create_user(is_staff=True)
    admin_token = data_fixture.generate_token(user=admin_user)

    response = api_client.get(
        reverse("api:admin:build:build"),
        format="json",
        HTTP_AUTHORIZATION=f"JWT {admin_token}",
    )
    assert response.status_code == HTTP_200_OK
    assert response.json() == {
        "version": "v0.13.0",
        "commit": "8b38f7dc832a689794023a21ee21e01772ec28de",
        "build_date": "2026-09-18T10:34:30Z",
        "baserow_version": VERSION,
    }


@pytest.mark.django_db
@override_settings(
    DEBUG=True,
    BASEROW_BUILD_VERSION="",
    BASEROW_BUILD_COMMIT="",
    BASEROW_BUILD_DATE="",
)
def test_admin_build_info_reports_blanks_for_a_development_build(
    api_client, data_fixture
):
    admin_user = data_fixture.create_user(is_staff=True)
    admin_token = data_fixture.generate_token(user=admin_user)

    response = api_client.get(
        reverse("api:admin:build:build"),
        format="json",
        HTTP_AUTHORIZATION=f"JWT {admin_token}",
    )
    assert response.status_code == HTTP_200_OK
    assert response.json() == {
        "version": "",
        "commit": "",
        "build_date": "",
        "baserow_version": VERSION,
    }
