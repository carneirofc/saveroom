import pytest

from baserow.core.action.signals import ActionCommandType
from baserow.core.audit_log.handler import AuditLogHandler
from baserow.core.audit_log.models import AUTH_COMMAND_TYPE, AuditLogEntry
from baserow.core.user.actions import SignInUserActionType


@pytest.mark.django_db
def test_log_action_creates_entry(data_fixture):
    user = data_fixture.create_user()
    workspace = data_fixture.create_workspace(user=user)

    entry = AuditLogHandler().log_action(
        user,
        SignInUserActionType,
        {"foo": "bar"},
        ActionCommandType.DO.value,
        workspace,
        ip_address="1.2.3.4",
    )

    assert AuditLogEntry.objects.count() == 1
    assert entry.user_id == user.id
    assert entry.user_email == user.email
    assert entry.workspace_id == workspace.id
    assert entry.ip_address == "1.2.3.4"
    assert entry.action_type == SignInUserActionType.type
    assert entry.command_type == ActionCommandType.DO.value
    assert entry.data == {"foo": "bar"}


@pytest.mark.django_db
def test_log_action_falls_back_when_description_fails(data_fixture):
    user = data_fixture.create_user()

    class BrokenActionType:
        type = "broken"

        @classmethod
        def get_long_description(cls, params_dict, *args, **kwargs):
            raise ValueError("boom")

    entry = AuditLogHandler().log_action(
        user, BrokenActionType, {"a": 1}, ActionCommandType.DO.value, None
    )

    assert entry.description == str({"a": 1})


@pytest.mark.django_db
def test_log_auth_event_sign_in_failed(data_fixture):
    entry = AuditLogHandler().log_auth_event(
        user=None,
        event_type="sign_in_failed",
        ip_address="9.9.9.9",
        user_email="someone@example.com",
    )

    assert entry.user_id is None
    assert entry.user_email == "someone@example.com"
    assert entry.action_type == "sign_in_failed"
    assert entry.command_type == AUTH_COMMAND_TYPE
    assert "someone@example.com" in entry.description


@pytest.mark.django_db
def test_log_auth_event_sign_out(data_fixture):
    user = data_fixture.create_user()

    entry = AuditLogHandler().log_auth_event(
        user=user, event_type="sign_out", ip_address="9.9.9.9"
    )

    assert entry.user_id == user.id
    assert entry.action_type == "sign_out"
    assert entry.command_type == AUTH_COMMAND_TYPE
