from baserow.core.exceptions import PermissionDenied, PermissionException


class DatabaseAccessDeniedError(PermissionDenied):
    """
    Raised when a member's in-app access level doesn't include the operation. It is a
    `PermissionDenied`, so callers that refuse on that (like websocket page
    subscriptions) refuse instead of erroring.
    """

    def __init__(self, user, workspace, level, operation_name, *args, **kwargs):
        self.user = user
        self.workspace = workspace
        self.level = level
        self.operation_name = operation_name
        # Skip `PermissionDenied`'s actor-based message.
        PermissionException.__init__(
            self,
            f"The user {user} with access level {level} isn't allowed to perform "
            f"{operation_name} in {workspace}.",
            *args,
            **kwargs,
        )


class InvalidAccessScope(Exception):
    """Raised when the grant scope doesn't exist or isn't in the workspace."""


class InvalidAccessSubject(Exception):
    """Raised when a grant subject isn't a member or team of the workspace."""
