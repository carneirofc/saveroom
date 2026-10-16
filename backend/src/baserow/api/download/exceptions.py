from baserow.core.storage import get_storage_backend_description


class DownloadTokenInvalid(Exception):
    """Raised when a download token is missing, malformed or was tampered with."""


class DownloadTokenExpired(Exception):
    """Raised when a download token is well formed but older than its max age."""


class ExportFileExpired(Exception):
    """
    Raised when the file behind an export or a backup is gone because it aged out of
    its retention window. This is the ordinary, expected case, and is deliberately
    kept apart from a file that went missing while it should still have been there.
    """


class ExportFileMissingFromStorage(Exception):
    """
    Raised when an export or backup that is still inside its retention window has no
    file in the storage. The instance wrote that file itself, so this is a server
    fault, and the message says so instead of claiming the file was not found.

    The concrete storage configuration is only spelled out for staff: it names
    MEDIA_ROOT or the bucket, which a regular member has no use for and should not be
    shown. Everyone else is told it is a server side problem and who to talk to.
    """

    def __init__(self, path: str, include_configuration_details: bool = False):
        self.path = path
        message = (
            "The export completed, but its file is no longer in the server's file "
            "storage even though it has not expired yet. This means the file storage "
            "is misconfigured"
        )
        if include_configuration_details:
            message += f": {get_storage_backend_description()}."
        else:
            message += (
                ". Please contact an administrator, the server logs and the "
                "instance health page have the details."
            )
        super().__init__(message)
