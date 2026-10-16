from django.dispatch import receiver

from baserow.core.action.signals import action_done

from .handler import AuditLogHandler


@receiver(action_done)
def audit_log_action_receiver(
    sender,
    user,
    action_type,
    action_params,
    action_timestamp,
    action_command_type,
    workspace,
    **kwargs,
):
    """
    Persists a permanent `AuditLogEntry` for every `action_done` signal. This is an
    additional receiver alongside the existing `log_action_receiver` in
    `baserow.core.action.signals`, which only logs to loguru: that receiver is left
    untouched.
    """

    AuditLogHandler().log_action(
        user,
        action_type,
        action_params,
        action_command_type.value,
        workspace,
    )
