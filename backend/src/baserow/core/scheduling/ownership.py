from django.contrib.auth.models import AbstractUser

from baserow.core.models import WORKSPACE_USER_PERMISSION_ADMIN, WorkspaceUser


def can_manage_schedule(user: AbstractUser, schedule) -> bool:
    """
    Tells whether a user may change, delete or manually run a schedule. A schedule
    runs with the permissions of its owner, so only the owner, an admin of the
    schedule's workspace or a staff member may do so.

    :param user: The user asking.
    :param schedule: Any schedule model with `user_id` and `workspace_id`.
    """

    if user.id == schedule.user_id or user.is_staff:
        return True

    return WorkspaceUser.objects.filter(
        user_id=user.id,
        workspace_id=schedule.workspace_id,
        permissions=WORKSPACE_USER_PERMISSION_ADMIN,
    ).exists()
