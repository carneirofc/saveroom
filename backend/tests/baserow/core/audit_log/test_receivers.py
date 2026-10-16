from datetime import datetime, timezone

import pytest

from baserow.core.action.signals import ActionCommandType, action_done
from baserow.core.audit_log.models import AuditLogEntry
from baserow.core.user.actions import SignInUserActionType


@pytest.mark.django_db
def test_action_done_signal_creates_audit_log_entry(data_fixture):
    user = data_fixture.create_user()
    workspace = data_fixture.create_workspace(user=user)

    action_done.send(
        sender=SignInUserActionType,
        user=user,
        action_type=SignInUserActionType,
        action_params={"some": "param"},
        action_command_type=ActionCommandType.DO,
        action_timestamp=datetime.now(tz=timezone.utc),
        workspace=workspace,
        session="test-session",
        scope="root",
        action_group=None,
        action_uuid="00000000-0000-0000-0000-000000000000",
    )

    entry = AuditLogEntry.objects.get()
    assert entry.user_id == user.id
    assert entry.workspace_id == workspace.id
    assert entry.action_type == SignInUserActionType.type
    assert entry.command_type == ActionCommandType.DO.value
    assert entry.data == {"some": "param"}
