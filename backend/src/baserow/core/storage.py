import logging
from io import BytesIO
from typing import BinaryIO, Optional

from django.conf import settings
from django.core.files.storage import Storage, default_storage
from django.http import FileResponse

# This import is necessary to handle the creation of zip files in a standardized way
# across the application. The ZipStream library is used to manage zip file streams
# efficiently, and we alias it as ExportZipFile for clarity and consistency.
from zipstream import ZipStream as ExportZipFile  # noqa

logger = logging.getLogger(__name__)


class FileNotFoundInStorage(Exception):
    """
    Raised when a file the database says should exist is not in the storage.

    This is never a "not found" from the user's point of view: the instance wrote the
    file itself, so either it expired (the caller knows that from the record) or the
    storage backend is misconfigured and the file was written somewhere this process
    cannot see.
    """

    def __init__(self, path: str):
        self.path = path
        super().__init__(f"The file '{path}' is not present in the storage.")


class StorageUnavailable(Exception):
    """
    Raised when the storage backend itself could not be reached or refused the
    operation: an unreachable endpoint, wrong credentials, missing permissions.
    """

    def __init__(self, path: str, original_exception: Exception):
        self.path = path
        self.original_exception = original_exception
        super().__init__(
            f"The storage backend could not be reached while accessing '{path}': "
            f"{type(original_exception).__name__}."
        )


def get_default_storage() -> Storage:
    """
    Returns the default storage. This method is mainly used to have
    a single point of entry for the default storage, so it's easier to
    test and mock.

    :return: The django default storage.
    """

    return default_storage


def get_storage_backend_description(storage: Optional[Storage] = None) -> str:
    """
    A short, operator facing description of where files are being kept, used in the
    error messages of downloads that could not find their file. It names the concrete
    misconfiguration rather than leaving the reader with "file not found".

    :param storage: The storage to describe, the default storage when not given.
    :return: A sentence describing the configured storage backend.
    """

    backend = settings.STORAGES["default"]["BACKEND"]

    if backend == "django.core.files.storage.FileSystemStorage":
        return (
            f"files are stored on the local filesystem at MEDIA_ROOT "
            f"('{settings.MEDIA_ROOT}'). When the web and worker processes run in "
            f"separate containers, MEDIA_ROOT must be a volume shared by both (a "
            f"ReadWriteMany claim on Kubernetes), or object storage must be "
            f"configured instead"
        )

    bucket = (
        getattr(settings, "AWS_STORAGE_BUCKET_NAME", None)
        or getattr(settings, "GS_BUCKET_NAME", None)
        or getattr(settings, "AZURE_CONTAINER", None)
    )
    if bucket:
        return f"files are stored in the '{bucket}' bucket by {backend}"

    return f"files are stored by {backend}"


class _StreamingFileResponse(FileResponse):
    """
    A `FileResponse` that reads in larger blocks than Django's 4096 byte default.

    `block_size` is consumed by `_set_streaming_content` during `__init__`, so it has
    to be set before calling super, not afterwards. At 4096 bytes a multi gigabyte
    backup is hundreds of thousands of chunks through the ASGI send path.
    """

    def __init__(self, *args, **kwargs):
        self.block_size = settings.BASEROW_EXPORT_DOWNLOAD_BLOCK_SIZE
        super().__init__(*args, **kwargs)


def check_file_in_storage(
    path: str, storage: Optional[Storage] = None
) -> Optional[int]:
    """
    Checks that a file is really in the storage and returns its size.

    Split out of `stream_file_from_storage` so a caller can answer a HEAD request, or
    otherwise find out whether a download would work, without opening the file.

    :param path: The path of the file within the storage.
    :param storage: The storage to check, the default storage when not given.
    :raises FileNotFoundInStorage: When the storage does not hold the file.
    :raises StorageUnavailable: When the storage backend could not be reached.
    :return: The size in bytes, or None when the storage could not report one.
    """

    storage = storage or get_default_storage()

    try:
        file_exists = storage.exists(path)
    except Exception as exc:  # noqa: BLE001 - any backend error means "unavailable"
        logger.exception("Could not check whether '%s' exists in the storage.", path)
        raise StorageUnavailable(path, exc) from exc

    if not file_exists:
        raise FileNotFoundInStorage(path)

    try:
        return storage.size(path)
    except Exception:  # noqa: BLE001 - a missing length only costs the progress bar
        logger.warning("Could not determine the size of '%s' in the storage.", path)
        return None


def stream_file_from_storage(
    path: str, download_name: str, storage: Optional[Storage] = None
) -> FileResponse:
    """
    Streams a file straight out of the storage as an attachment, without copying it
    anywhere first. This is what makes downloads work regardless of whether the
    storage is a shared volume or an object store that the browser cannot reach.

    Note that this costs three round trips on a remote storage (`exists`, `size` and
    `open`), which is acceptable for a download but would not be inside a loop. Under
    ASGI the response occupies a thread pool slot for the duration of the transfer.

    :param path: The path of the file within the storage.
    :param download_name: The file name offered to the browser.
    :param storage: The storage to read from, the default storage when not given.
    :raises FileNotFoundInStorage: When the storage does not hold the file.
    :raises StorageUnavailable: When the storage backend could not be reached.
    :return: A streaming response that closes the file handle when it is done.
    """

    storage = storage or get_default_storage()

    size = check_file_in_storage(path, storage)

    try:
        file_handle = storage.open(path, "rb")
    except FileNotFoundError as exc:
        raise FileNotFoundInStorage(path) from exc
    except Exception as exc:  # noqa: BLE001 - see above
        logger.exception("Could not open '%s' from the storage.", path)
        raise StorageUnavailable(path, exc) from exc

    # `FileResponse` builds the Content-Disposition header itself, including the
    # RFC 5987 `filename*` form for non ascii names, and closes the file handle once
    # the response is closed.
    response = _StreamingFileResponse(
        file_handle,
        as_attachment=True,
        filename=download_name,
        content_type="application/octet-stream",
    )

    # `FileResponse` derives the length from `getbuffer()` or `os.fstat(fileno())`,
    # neither of which the S3 file object supports. Without setting it explicitly the
    # response falls back to chunked encoding and the browser shows no progress.
    if size is not None:
        response["Content-Length"] = size

    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store"
    response["Referrer-Policy"] = "same-origin"
    response["Content-Security-Policy"] = (
        "sandbox; default-src 'none'; script-src 'none'; object-src 'none'; "
        "base-uri 'none'"
    )

    return response


class OverwritingStorageHandler:
    def __init__(self, storage=None):
        self.storage = storage or get_default_storage()

    def save(self, name, content):
        if self.storage.exists(name):
            self.storage.delete(name)
        self.storage.save(name, content)


def _create_storage_dir_if_missing_and_open(storage_location, storage=None) -> BinaryIO:
    """
    Attempts to open the provided storage location in binary overwriting write mode.
    If it encounters a FileNotFound error will attempt to create the folder structure
    leading upto to the storage location and then open again.

    :param storage_location: The storage location to open and ensure folders for.
    :param storage: The storage to use, if None will use the default storage.
    :return: The open file descriptor for the storage_location
    """

    storage = storage or get_default_storage()

    try:
        return storage.open(storage_location, "wb+")
    except FileNotFoundError:
        # django's file system storage will not attempt to creating a missing
        # EXPORT_FILES_DIRECTORY and instead will throw a FileNotFoundError.
        # So we first save an empty file which will create any missing directories
        # and then open again.
        storage.save(storage_location, BytesIO())
        return storage.open(storage_location, "wb")
