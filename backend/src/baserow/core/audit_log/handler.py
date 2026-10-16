from typing import Any, Dict, Optional

from django.contrib.auth.models import AbstractUser

from baserow.core.models import Workspace

from .models import AUTH_COMMAND_TYPE, AuditLogEntry


class AuditLogHandler:
    """
    Writes permanent `AuditLogEntry` rows. This is an internal, system level side
    effect: it performs no permission checks of its own.
    """

    def log_action(
        self,
        user: Optional[AbstractUser],
        action_type: Any,
        action_params: Dict[str, Any],
        action_command_type: str,
        workspace: Optional[Workspace],
        ip_address: Optional[str] = None,
    ) -> AuditLogEntry:
        """
        Records an entry for an `action_done` signal.

        :param user: The user the action was performed by, if any.
        :param action_type: The registered `ActionType` (class or instance) the
            action was performed with.
        :param action_params: The raw, JSON-serializable params of the action.
        :param action_command_type: One of `ActionCommandType`'s values (DO/UNDO/
            REDO).
        :param workspace: The workspace the action took place in, if any.
        :param ip_address: The IP address the request originated from, if known.
        :return: The created entry.
        """

        try:
            description = action_type.get_long_description(action_params)
        except Exception:
            # A broken description must never prevent the audit trail from being
            # written.
            description = str(action_params)

        # `AuditLogEntry.user` is a real FK: an `AnonymousUser` (e.g. a public form
        # submission) isn't a `User` instance and can't be assigned to it, so only
        # attribute the entry to actual authenticated users.
        attributed_user = user if user is not None and user.is_authenticated else None

        return AuditLogEntry.objects.create(
            user=attributed_user,
            user_email=getattr(attributed_user, "email", "") or "",
            workspace=workspace,
            ip_address=ip_address,
            action_type=action_type.type,
            command_type=action_command_type,
            description=description,
            data=action_params or {},
        )

    def log_auth_event(
        self,
        user: Optional[AbstractUser],
        event_type: str,
        ip_address: Optional[str] = None,
        user_email: Optional[str] = None,
    ) -> AuditLogEntry:
        """
        Records a synthetic auth event (sign-in failure, sign-out) that does not go
        through the `action_done` signal.

        :param user: The user the event relates to, if known/authenticated.
        :param event_type: A short event name, e.g. "sign_in_failed" or "sign_out".
        :param ip_address: The IP address the request originated from, if known.
        :param user_email: The email the event relates to, used when `user` is not
            known (e.g. a failed sign-in with an unknown or wrong email).
        :return: The created entry.
        """

        resolved_email = user_email or getattr(user, "email", "") or ""

        if event_type == "sign_in_failed":
            description = f"Sign-in failed for {resolved_email or 'unknown user'}"
        elif event_type == "sign_out":
            description = f"{resolved_email or 'A user'} signed out"
        else:
            description = event_type

        return AuditLogEntry.objects.create(
            user=user,
            user_email=resolved_email,
            workspace=None,
            ip_address=ip_address,
            action_type=event_type,
            command_type=AUTH_COMMAND_TYPE,
            description=description,
            data={},
        )
