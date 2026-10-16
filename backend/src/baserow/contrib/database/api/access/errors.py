from rest_framework.status import HTTP_400_BAD_REQUEST, HTTP_404_NOT_FOUND

ERROR_ACCESS_SCOPE_DOES_NOT_EXIST = (
    "ERROR_ACCESS_SCOPE_DOES_NOT_EXIST",
    HTTP_404_NOT_FOUND,
    "The requested workspace, database or table does not exist.",
)
ERROR_INVALID_ACCESS_SUBJECT = (
    "ERROR_INVALID_ACCESS_SUBJECT",
    HTTP_400_BAD_REQUEST,
    "Access can only be given to members and teams of the workspace.",
)
