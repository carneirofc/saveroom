from django.db import migrations


class Migration(migrations.Migration):
    """
    Workspace membership, teams and database/table access are managed in the app, so
    the env-declared granular roles and the SSO membership tracking are dropped. Members
    that had a granular role become unrestricted members; restrict them again with
    in-app access grants.
    """

    dependencies = [
        ("core", "0121_teams"),
    ]

    operations = [
        migrations.RemoveField(model_name="workspaceuser", name="role"),
        migrations.DeleteModel(name="Role"),
        migrations.DeleteModel(name="OIDCSsoWorkspaceMembership"),
    ]
