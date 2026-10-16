import re

from django.http import HttpResponse

from baserow.core.storage import (
    FileNotFoundInStorage,
    StorageUnavailable,
    check_file_in_storage,
    stream_file_from_storage,
)

from .errors import (
    ERROR_DOWNLOAD_TOKEN_EXPIRED,
    ERROR_DOWNLOAD_TOKEN_INVALID,
    ERROR_EXPORT_FILE_EXPIRED,
    ERROR_EXPORT_FILE_MISSING_FROM_STORAGE,
    ERROR_STORAGE_UNAVAILABLE,
)
from .exceptions import (
    DownloadTokenExpired,
    DownloadTokenInvalid,
    ExportFileExpired,
    ExportFileMissingFromStorage,
)
from .tokens import check_download_token_matches

# Every download view maps the same set of failures, so that a client can tell an
# archive that aged out apart from a server that lost it.
DOWNLOAD_EXCEPTIONS = {
    DownloadTokenInvalid: ERROR_DOWNLOAD_TOKEN_INVALID,
    DownloadTokenExpired: ERROR_DOWNLOAD_TOKEN_EXPIRED,
    ExportFileExpired: ERROR_EXPORT_FILE_EXPIRED,
    ExportFileMissingFromStorage: ERROR_EXPORT_FILE_MISSING_FROM_STORAGE,
    StorageUnavailable: ERROR_STORAGE_UNAVAILABLE,
}

_UNSAFE_FILE_NAME_CHARACTERS = re.compile(r"[\\/\r\n\x00]")


def sanitize_download_name(requested_name: str, fallback: str) -> str:
    """
    Makes a client supplied download name safe to put in a Content-Disposition header.

    The friendly name of a table export only exists in the browser -- the stored file
    is a uuid -- so the client passes it along. It never reaches the storage, it only
    decides what the browser calls the saved file.

    :param requested_name: The name the client asked for, may be empty.
    :param fallback: The name to use when the request did not carry a usable one.
    :return: A safe file name.
    """

    if not requested_name:
        return fallback

    cleaned = _UNSAFE_FILE_NAME_CHARACTERS.sub("", requested_name).strip().strip(".")

    return cleaned[:255] or fallback


def serve_export_file(
    request,
    download_type: str,
    object_id: int,
    storage_path: str,
    download_name: str,
    expired: bool,
    expiry_message: str,
    head_only: bool = False,
):
    """
    Serves an exported file straight out of the storage, and turns every way that can
    fail into a distinct, honest answer.

    :param request: The request being served.
    :param download_type: The download type the view serves, checked against the
        token so a link cannot be replayed on another object.
    :param object_id: The id of the object being downloaded.
    :param storage_path: Where the file lives in the storage, None when the record
        never had one.
    :param download_name: The name the browser should save the file as.
    :param expired: Whether the record says the file has aged out of its retention.
    :param expiry_message: What to tell the user when it has.
    :param head_only: Answer with headers only, used for the client's preflight.
    :return: A streaming response, or an empty response when `head_only`.
    """

    check_download_token_matches(request, download_type, object_id)

    if not storage_path or expired:
        raise ExportFileExpired(expiry_message)

    # A file that is gone while the record says it should still be there is not a
    # "not found": this instance wrote it and then lost it, which is a server fault
    # and is reported as one. The configuration is only spelled out for staff.
    include_details = bool(getattr(request.user, "is_staff", False))

    if head_only:
        try:
            size = check_file_in_storage(storage_path)
        except FileNotFoundInStorage as exc:
            raise ExportFileMissingFromStorage(exc.path, include_details) from exc

        response = HttpResponse(status=200)
        response["Content-Type"] = "application/octet-stream"
        response["Content-Disposition"] = f'attachment; filename="{download_name}"'
        if size is not None:
            response["Content-Length"] = size
        return response

    try:
        return stream_file_from_storage(storage_path, download_name)
    except FileNotFoundInStorage as exc:
        raise ExportFileMissingFromStorage(exc.path, include_details) from exc
