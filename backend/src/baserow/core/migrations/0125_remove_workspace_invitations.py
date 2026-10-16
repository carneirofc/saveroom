from django.db import migrations

INVITATION_NOTIFICATION_TYPES = [
    "workspace_invitation_created",
    "workspace_invitation_accepted",
    "workspace_invitation_rejected",
]


def delete_invitation_notifications(apps, schema_editor):
    Notification = apps.get_model("core", "Notification")
    Notification.objects.filter(type__in=INVITATION_NOTIFICATION_TYPES).delete()


class Migration(migrations.Migration):
    """
    Workspace invitations are removed: admins add registered users directly. Pending
    invitations and the notifications about them are dropped.
    """

    dependencies = [
        (
            "core",
            "0124_rename_core_auditl_created_9c5e8b_idx_core_auditl_created_441a84_idx_and_more",
        ),
    ]

    operations = [
        migrations.RunPython(
            delete_invitation_notifications, migrations.RunPython.noop
        ),
        migrations.RemoveField(
            model_name="settings",
            name="allow_signups_via_workspace_invitations",
        ),
        migrations.DeleteModel(name="WorkspaceInvitation"),
    ]
