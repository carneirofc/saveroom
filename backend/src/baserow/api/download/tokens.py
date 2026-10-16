import logging
from dataclasses import asdict, dataclass

from django.conf import settings
from django.core import signing

from .exceptions import DownloadTokenExpired, DownloadTokenInvalid

logger = logging.getLogger(__name__)

# A salt of its own, so a download token can never be swapped for the session payload
# signed in `baserow.core.user.utils` or for any other signed value.
DOWNLOAD_TOKEN_SALT = "baserow.export.download"

TABLE_EXPORT_DOWNLOAD = "table_export"
WORKSPACE_EXPORT_DOWNLOAD = "workspace_export"
BACKUP_DOWNLOAD = "backup"


@dataclass
class DownloadTokenPayload:
    user_id: int
    type: str
    id: int


def sign_download_token(user_id: int, download_type: str, object_id: int) -> str:
    """
    Signs a download link for one user and one object.

    The token only says who the link was minted for and what it points at. It is not
    an authorisation: the view still runs the same handler scoping the regular
    authenticated path runs, so a user who lost access in the meantime is refused.

    :param user_id: The user the link is for.
    :param download_type: One of the `*_DOWNLOAD` constants in this module.
    :param object_id: The id of the job or resource the link points at.
    :return: The signed token to put in the query string.
    """

    return signing.TimestampSigner(salt=DOWNLOAD_TOKEN_SALT).sign_object(
        asdict(DownloadTokenPayload(user_id, download_type, object_id))
    )


def unsign_download_token(token: str) -> DownloadTokenPayload:
    """
    Verifies a download token and returns what it claims.

    :param token: The token taken from the query string.
    :raises DownloadTokenExpired: When the token is older than its max age.
    :raises DownloadTokenInvalid: When the token is missing, malformed or tampered
        with.
    :return: The payload the token carries.
    """

    if not token:
        raise DownloadTokenInvalid("No download token was provided.")

    try:
        payload = signing.TimestampSigner(salt=DOWNLOAD_TOKEN_SALT).unsign_object(
            token, max_age=settings.BASEROW_EXPORT_DOWNLOAD_TOKEN_MAX_AGE_SECONDS
        )
    except signing.SignatureExpired as exc:
        raise DownloadTokenExpired("The download token has expired.") from exc
    except signing.BadSignature as exc:
        raise DownloadTokenInvalid("The download token is not valid.") from exc

    try:
        return DownloadTokenPayload(
            user_id=int(payload["user_id"]),
            type=str(payload["type"]),
            id=int(payload["id"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise DownloadTokenInvalid("The download token is malformed.") from exc


def check_download_token_matches(request, expected_type: str, expected_id: int) -> None:
    """
    Makes sure a request that authenticated with a download token presented it at the
    route it was minted for. Without this a token for one backup would download
    another one, or a table export token would work on the backup endpoint.

    Requests that authenticated some other way (a JWT or an API client key) carry no
    payload and pass straight through; their own permission checks already ran.

    :param request: The request to check.
    :param expected_type: The download type the view serves.
    :param expected_id: The id of the object the view is about to serve.
    :raises DownloadTokenInvalid: When the token points at something else.
    """

    payload = getattr(request, "download_token_payload", None)

    if payload is None:
        return

    if payload.type != expected_type or payload.id != int(expected_id):
        logger.warning(
            "A download token for %s %s was presented at %s %s.",
            payload.type,
            payload.id,
            expected_type,
            expected_id,
        )
        raise DownloadTokenInvalid("The download token is not valid for this file.")
