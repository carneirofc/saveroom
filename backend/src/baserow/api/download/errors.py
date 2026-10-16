from rest_framework.status import (
    HTTP_401_UNAUTHORIZED,
    HTTP_410_GONE,
    HTTP_500_INTERNAL_SERVER_ERROR,
    HTTP_503_SERVICE_UNAVAILABLE,
)

ERROR_DOWNLOAD_TOKEN_INVALID = (
    "ERROR_DOWNLOAD_TOKEN_INVALID",
    HTTP_401_UNAUTHORIZED,
    "The download link is not valid.",
)

ERROR_DOWNLOAD_TOKEN_EXPIRED = (
    "ERROR_DOWNLOAD_TOKEN_EXPIRED",
    HTTP_401_UNAUTHORIZED,
    "The download link has expired. Open the list again to get a fresh one.",
)

ERROR_EXPORT_FILE_EXPIRED = (
    "ERROR_EXPORT_FILE_EXPIRED",
    HTTP_410_GONE,
    "{e}",
)

# Deliberately a server error and not a 404: the instance wrote this file itself and
# is still within the window where it promised to keep it, so it losing the file is a
# fault of the instance, not a request for something that never existed.
ERROR_EXPORT_FILE_MISSING_FROM_STORAGE = (
    "ERROR_EXPORT_FILE_MISSING_FROM_STORAGE",
    HTTP_500_INTERNAL_SERVER_ERROR,
    "{e}",
)

# The exception carries the storage path and the underlying error, which are logged
# but never returned: they would leak the endpoint and the internal layout.
ERROR_STORAGE_UNAVAILABLE = (
    "ERROR_STORAGE_UNAVAILABLE",
    HTTP_503_SERVICE_UNAVAILABLE,
    "The server's file storage could not be reached, so the file could not be "
    "downloaded. Try again, and contact an administrator if it keeps happening.",
)
