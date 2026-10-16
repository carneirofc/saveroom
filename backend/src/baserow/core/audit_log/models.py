from django.conf import settings
from django.db import models

from baserow.core.action.signals import ActionCommandType

# The two synthetic events logged outside of the `action_done` signal (Baserow's
# auth flow is JWT based, so Django's session login signals never fire here).
AUTH_COMMAND_TYPE = "AUTH"

# Every `action_type` an entry can hold that is not a registered `ActionType.type`.
# A new `log_auth_event` caller must be listed here, or the value it writes will be
# missing from the audit log's action type filter.
AUTH_EVENT_TYPES = ["sign_in_failed", "sign_out"]

COMMAND_TYPE_CHOICES = [(c.value, c.value) for c in ActionCommandType] + [
    (AUTH_COMMAND_TYPE, AUTH_COMMAND_TYPE)
]


class AuditLogEntry(models.Model):
    """
    A permanent, staff-facing record of an action performed in Baserow.

    Populated by a signal receiver listening to `baserow.core.action.signals
    .action_done`, which fires for nearly every mutating operation in the app
    (rows, fields, tables, views, applications, workspace membership, teams,
    snapshots, import/export, trash, webhooks, sign-in, ...), plus two explicit
    hooks for sign-out and failed sign-in.

    This table is permanent and must NEVER be referenced by
    `baserow.core.action.tasks.cleanup_old_actions`, or any other purge task: unlike
    the `Action` model it is not undo/redo bookkeeping, it is the audit trail itself.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        help_text="The user that performed the action. Null if the user was deleted "
        "or the action could not be attributed to an authenticated user.",
    )
    user_email = models.CharField(
        max_length=254,
        blank=True,
        default="",
        help_text="A snapshot of the user's email at the time of the action, so the "
        "entry stays meaningful after the user is deleted.",
    )
    workspace = models.ForeignKey(
        "core.Workspace",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        help_text="The workspace the action was performed in, if any.",
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="The IP address the request originated from, if known.",
    )
    action_type = models.CharField(
        max_length=100,
        db_index=True,
        help_text="The registered ActionType.type, or a synthetic event name such "
        "as 'sign_in_failed' or 'sign_out'.",
    )
    command_type = models.CharField(
        max_length=10,
        choices=COMMAND_TYPE_CHOICES,
        help_text="Whether the action was done, undone, redone, or is a synthetic "
        "auth event.",
    )
    description = models.TextField(
        blank=True,
        default="",
        help_text="A human readable description of the action.",
    )
    data = models.JSONField(
        default=dict,
        blank=True,
        help_text="The raw action parameters, kept for audits that need detail "
        "beyond the description.",
    )
    created_on = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_on",)
        indexes = [
            models.Index(fields=["-created_on"]),
            models.Index(fields=["user"]),
            models.Index(fields=["workspace"]),
            models.Index(fields=["action_type"]),
        ]

    def __str__(self) -> str:
        return (
            f"AuditLogEntry(user_email={self.user_email}, action_type="
            f"{self.action_type}, workspace_id={self.workspace_id}, "
            f"created_on={self.created_on})"
        )
