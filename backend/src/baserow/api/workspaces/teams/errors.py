from rest_framework.status import HTTP_400_BAD_REQUEST, HTTP_404_NOT_FOUND

ERROR_TEAM_DOES_NOT_EXIST = (
    "ERROR_TEAM_DOES_NOT_EXIST",
    HTTP_404_NOT_FOUND,
    "The requested team does not exist.",
)
ERROR_TEAM_NAME_NOT_UNIQUE = (
    "ERROR_TEAM_NAME_NOT_UNIQUE",
    HTTP_400_BAD_REQUEST,
    "A team with this name already exists in the workspace.",
)
ERROR_TEAM_MEMBER_NOT_IN_WORKSPACE = (
    "ERROR_TEAM_MEMBER_NOT_IN_WORKSPACE",
    HTTP_400_BAD_REQUEST,
    "Only members of the workspace can be added to its teams.",
)
