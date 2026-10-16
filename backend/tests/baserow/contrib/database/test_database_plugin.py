import pytest

from baserow.contrib.database.models import Database
from baserow.contrib.database.plugins import DatabasePlugin


@pytest.mark.django_db
def test_user_created_without_workspace_returns(data_fixture):
    # If the user registered without a template, and the Setting
    # `allow_global_workspace_creation` is set to `False`, then no `Workspace` will
    # be created for this `user`.
    plugin = DatabasePlugin()
    user = data_fixture.create_user()
    assert plugin.user_created(user) is None
    assert Database.objects.count() == 0


@pytest.mark.django_db
def test_user_created_with_template_returns(data_fixture):
    # If the user created an account with a template we don't want to create the
    # initial data in the workspace because the template provides it.
    plugin = DatabasePlugin()
    user = data_fixture.create_user()
    workspace = data_fixture.create_workspace(user=user)

    template = data_fixture.create_template(workspace=workspace)
    assert plugin.user_created(user, workspace, template=template) is None
    assert Database.objects.count() == 0
