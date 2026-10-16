import json

from django.urls import reverse

import pytest
from rest_framework.status import HTTP_200_OK, HTTP_401_UNAUTHORIZED

from baserow.core.data_destinations.config import parse_data_destinations_env


@pytest.mark.django_db
def test_list_data_destinations_hides_credentials(api_client, data_fixture, settings):
    settings.BASEROW_DATA_DESTINATIONS = parse_data_destinations_env(
        json.dumps(
            [
                {
                    "name": "lake",
                    "type": "s3",
                    "bucket": "private-bucket",
                    "access_key_id": "key",
                    "secret_access_key": "top-secret",
                    "purposes": ["datalake"],
                }
            ]
        )
    )
    _, token = data_fixture.create_user_and_token()

    response = api_client.get(
        reverse("api:data_destinations:list"),
        HTTP_AUTHORIZATION=f"JWT {token}",
    )

    assert response.status_code == HTTP_200_OK
    assert response.json() == [
        {
            "name": "lake",
            "type": "s3",
            "purposes": ["datalake"],
            "allow_trust_public_key": False,
        }
    ]
    assert "top-secret" not in response.content.decode()
    assert "private-bucket" not in response.content.decode()


@pytest.mark.django_db
def test_list_data_destinations_requires_authentication(api_client):
    response = api_client.get(reverse("api:data_destinations:list"))

    assert response.status_code == HTTP_401_UNAUTHORIZED
