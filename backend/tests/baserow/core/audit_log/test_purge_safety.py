from datetime import datetime, timedelta, timezone

from django.test.utils import override_settings

import pytest

from baserow.core.action.handler import ActionHandler
from baserow.core.action.models import Action
from baserow.core.audit_log.handler import AuditLogHandler
from baserow.core.audit_log.models import AuditLogEntry
from baserow.core.user.actions import SignInUserActionType


@pytest.mark.django_db
@override_settings(MINUTES_UNTIL_ACTION_CLEANED_UP=1)
def test_cleanup_old_actions_never_touches_audit_log_entries(data_fixture):
    user = data_fixture.create_user()

    old_action = Action.objects.create(
        user=user,
        type=SignInUserActionType.type,
        params={},
        scope="root",
    )
    old_timestamp = datetime.now(tz=timezone.utc) - timedelta(minutes=10)
    Action.objects.filter(id=old_action.id).update(updated_on=old_timestamp)

    entry = AuditLogHandler().log_action(user, SignInUserActionType, {}, "DO", None)

    ActionHandler.clean_up_old_undoable_actions()

    assert not Action.objects.filter(id=old_action.id).exists()
    assert AuditLogEntry.objects.filter(id=entry.id).exists()
