from django.dispatch import receiver

from baserow.core.signals import workspace_user_deleted

from .handler import TeamHandler


@receiver(workspace_user_deleted)
def remove_deleted_workspace_user_from_teams(sender, workspace_user, **kwargs):
    """A user leaving or removed from a workspace must not keep its team memberships."""

    TeamHandler().remove_user_from_workspace_teams(
        workspace_user.user, workspace_user.workspace_id
    )
