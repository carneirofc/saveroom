import pytest

from baserow.core.backups.operations import ListBackupSchedulesOperationType
from baserow.core.exceptions import PermissionDenied, UserNotInWorkspace
from baserow.core.handler import CoreHandler
from baserow.core.operations import ExportWorkspaceOperationType


@pytest.mark.django_db
def test_staff_bypasses_workspace_membership_for_backup_operations(data_fixture):
    staff_user = data_fixture.create_user(is_staff=True)
    workspace = data_fixture.create_workspace()  # staff_user is not a member

    assert (
        CoreHandler().check_permissions(
            staff_user,
            ExportWorkspaceOperationType.type,
            workspace=workspace,
            context=workspace,
        )
        is True
    )
    assert (
        CoreHandler().check_permissions(
            staff_user,
            ListBackupSchedulesOperationType.type,
            workspace=workspace,
            context=workspace,
        )
        is True
    )


@pytest.mark.django_db
def test_non_staff_non_member_still_denied_for_backup_operations(data_fixture):
    user = data_fixture.create_user()
    workspace = data_fixture.create_workspace()  # user is not a member

    with pytest.raises((UserNotInWorkspace, PermissionDenied)):
        CoreHandler().check_permissions(
            user,
            ExportWorkspaceOperationType.type,
            workspace=workspace,
            context=workspace,
        )


@pytest.mark.django_db
def test_regular_member_export_permission_is_unaffected(data_fixture):
    user = data_fixture.create_user()
    workspace = data_fixture.create_workspace(user=user)

    assert (
        CoreHandler().check_permissions(
            user,
            ExportWorkspaceOperationType.type,
            workspace=workspace,
            context=workspace,
        )
        is True
    )


@pytest.mark.django_db
def test_staff_sees_every_application_of_a_workspace_they_are_not_in(data_fixture):
    from baserow.core.models import Application
    from baserow.core.operations import ListApplicationsWorkspaceOperationType

    staff_user = data_fixture.create_user(is_staff=True)
    user = data_fixture.create_user()
    workspace = data_fixture.create_workspace()
    data_fixture.create_database_application(workspace=workspace)
    data_fixture.create_database_application(workspace=workspace)

    def visible(actor):
        return CoreHandler().filter_queryset(
            actor,
            ListApplicationsWorkspaceOperationType.type,
            Application.objects.filter(workspace=workspace),
            workspace=workspace,
        )

    assert visible(staff_user).count() == 2
    assert visible(user).count() == 0
