import pytest

from baserow.contrib.database.operations import ListTablesDatabaseTableOperationType
from baserow.core.cache import local_cache
from baserow.core.exceptions import PermissionException
from baserow.core.handler import CoreHandler
from baserow.core.operations import (
    ListApplicationsWorkspaceOperationType,
    ReadApplicationOperationType,
)
from baserow.core.permission_manager import (
    ApplicationTypeEnabledPermissionManagerType,
)
from baserow.core.service import CoreService


@pytest.mark.django_db
def test_nothing_is_decided_while_every_application_type_is_enabled(data_fixture):
    perm_manager = ApplicationTypeEnabledPermissionManagerType()
    user = data_fixture.create_user()
    workspace = data_fixture.create_workspace(user=user)
    database = data_fixture.create_database_application(workspace=workspace)

    assert perm_manager.get_disabled_application_types() == []
    assert (
        perm_manager.check_permissions(
            user,
            ReadApplicationOperationType.type,
            workspace=workspace,
            context=database,
        )
        is None
    )


@pytest.mark.django_db
def test_reading_an_application_of_a_disabled_type_is_denied(data_fixture):
    perm_manager = ApplicationTypeEnabledPermissionManagerType()
    user = data_fixture.create_user()
    workspace = data_fixture.create_workspace(user=user)
    database = data_fixture.create_database_application(workspace=workspace)
    dashboard = data_fixture.create_dashboard_application(workspace=workspace)

    data_fixture.update_settings(enable_database=False)

    assert perm_manager.get_disabled_application_types() == ["database"]

    with pytest.raises(PermissionException):
        perm_manager.check_permissions(
            user,
            ReadApplicationOperationType.type,
            workspace=workspace,
            context=database,
        )

    # A type that is still enabled is left to the other permission managers.
    assert (
        perm_manager.check_permissions(
            user,
            ReadApplicationOperationType.type,
            workspace=workspace,
            context=dashboard,
        )
        is None
    )


@pytest.mark.django_db
def test_an_operation_inside_a_disabled_application_is_denied(data_fixture):
    perm_manager = ApplicationTypeEnabledPermissionManagerType()
    user = data_fixture.create_user()
    workspace = data_fixture.create_workspace(user=user)
    database = data_fixture.create_database_application(workspace=workspace)

    data_fixture.update_settings(enable_database=False)

    # The context is a database rather than the base application, so the manager has
    # to walk the scope hierarchy up to the application to decide.
    with pytest.raises(PermissionException):
        perm_manager.check_permissions(
            user,
            ListTablesDatabaseTableOperationType.type,
            workspace=workspace,
            context=database,
        )


@pytest.mark.django_db
def test_an_operation_outside_any_application_is_not_decided(data_fixture):
    perm_manager = ApplicationTypeEnabledPermissionManagerType()
    user = data_fixture.create_user()
    workspace = data_fixture.create_workspace(user=user)

    data_fixture.update_settings(enable_database=False)

    assert (
        perm_manager.check_permissions(
            user,
            ListApplicationsWorkspaceOperationType.type,
            workspace=workspace,
            context=workspace,
        )
        is None
    )


@pytest.mark.django_db
def test_applications_of_a_disabled_type_are_filtered_out_of_the_listing(data_fixture):
    user = data_fixture.create_user()
    workspace = data_fixture.create_workspace(user=user)
    database = data_fixture.create_database_application(workspace=workspace)
    dashboard = data_fixture.create_dashboard_application(workspace=workspace)

    data_fixture.update_settings(enable_dashboard=False)

    applications = CoreService().list_applications_in_workspace(
        user, workspace, specific=False
    )
    assert [application.id for application in applications] == [database.id]

    # Nothing was deleted: enabling the type again brings the dashboard back.
    data_fixture.update_settings(enable_dashboard=True)
    local_cache.clear()

    applications = CoreService().list_applications_in_workspace(
        user, workspace, specific=False
    )
    assert sorted(application.id for application in applications) == sorted(
        [database.id, dashboard.id]
    )


@pytest.mark.django_db
def test_reading_an_application_of_a_disabled_type_is_denied_through_the_service(
    data_fixture,
):
    user = data_fixture.create_user()
    workspace = data_fixture.create_workspace(user=user)
    dashboard = data_fixture.create_dashboard_application(workspace=workspace)

    data_fixture.update_settings(enable_dashboard=False)

    with pytest.raises(PermissionException):
        CoreService().get_application(user, dashboard.id)

    assert CoreHandler().application_type_is_enabled("dashboard") is False
