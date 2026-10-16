from unittest.mock import call, patch

from django.shortcuts import reverse

import pytest
from freezegun import freeze_time
from rest_framework.status import HTTP_200_OK

from baserow.core.notification_types import BaserowVersionUpgradeNotificationType
from baserow.core.notifications.handler import NotificationHandler
from baserow.core.notifications.models import NotificationRecipient
from baserow.test_utils.helpers import AnyInt


@pytest.mark.django_db
@patch("baserow.core.notifications.signals.notification_created.send")
def test_baserow_version_upgrade_is_sent_as_broadcast_notification(
    mocked_notification_created, api_client, data_fixture
):
    user_1, token_1 = data_fixture.create_user_and_token()
    user_2, token_2 = data_fixture.create_user_and_token()
    workspace_1 = data_fixture.create_workspace(user=user_1)
    workspace_2 = data_fixture.create_workspace(user=user_2)

    with freeze_time("2023-07-06 12:00"):
        BaserowVersionUpgradeNotificationType.create_version_upgrade_broadcast_notification(
            "1.19", "/blog/release-notes/1.19"
        )

    mocked_notification_created.assert_called_once()
    args = mocked_notification_created.call_args
    notification = NotificationHandler.get_notification_by(user_1, broadcast=True)
    assert args == call(
        sender=NotificationHandler,
        notification=notification,
        notification_recipients=list(
            NotificationRecipient.objects.filter(
                recipient=None, notification=notification
            )
        ),
        user=None,
    )

    excepted_response = {
        "count": 1,
        "next": None,
        "previous": None,
        "results": [
            {
                "id": AnyInt(),
                "created_on": "2023-07-06T12:00:00Z",
                "type": BaserowVersionUpgradeNotificationType.type,
                "data": {
                    "version": "1.19",
                    "release_notes_url": "/blog/release-notes/1.19",
                },
                "read": False,
                "sender": None,
                "workspace": None,
            }
        ],
    }

    response = api_client.get(
        reverse("api:notifications:list", kwargs={"workspace_id": workspace_1.id}),
        HTTP_AUTHORIZATION=f"JWT {token_1}",
    )
    assert response.status_code == HTTP_200_OK
    assert response.json() == excepted_response

    response = api_client.get(
        reverse("api:notifications:list", kwargs={"workspace_id": workspace_2.id}),
        HTTP_AUTHORIZATION=f"JWT {token_2}",
    )
    assert response.status_code == HTTP_200_OK
    assert response.json() == excepted_response
