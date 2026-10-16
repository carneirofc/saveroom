from rest_framework.status import (
    HTTP_400_BAD_REQUEST,
    HTTP_401_UNAUTHORIZED,
    HTTP_404_NOT_FOUND,
)

ERROR_API_CLIENT_DOES_NOT_EXIST = (
    "ERROR_API_CLIENT_DOES_NOT_EXIST",
    HTTP_404_NOT_FOUND,
    "The requested API client does not exist.",
)
ERROR_API_CLIENT_KEY_DOES_NOT_EXIST = (
    "ERROR_API_CLIENT_KEY_DOES_NOT_EXIST",
    HTTP_404_NOT_FOUND,
    "The requested API client key does not exist.",
)
ERROR_API_CLIENT_DOES_NOT_BELONG_TO_USER = (
    "ERROR_API_CLIENT_DOES_NOT_BELONG_TO_USER",
    HTTP_401_UNAUTHORIZED,
    "The API client does not belong to the authenticated user.",
)
ERROR_INVALID_API_CLIENT_SCOPE = (
    "ERROR_INVALID_API_CLIENT_SCOPE",
    HTTP_400_BAD_REQUEST,
    "{e}",
)
