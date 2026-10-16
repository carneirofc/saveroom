import logging

from django.contrib.auth import get_user_model

from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from baserow.api.sessions import set_user_remote_addr_ip_from_request
from baserow.core.telemetry.utils import setup_user_in_baggage_and_spans

from .exceptions import DownloadTokenExpired, DownloadTokenInvalid
from .tokens import unsign_download_token

logger = logging.getLogger(__name__)

User = get_user_model()


class DownloadTokenAuthentication(BaseAuthentication):
    """
    Authenticates a download made with a signed `token` query parameter.

    A browser downloading through a plain anchor cannot send an Authorization header,
    which is the whole reason this exists. The token replaces what used to be a
    presigned object storage URL, so it is the same kind of short lived bearer
    capability, only scoped to a single object and a single user.

    A request without a `token` parameter is left alone, so JWT and API client
    authentication keep working on the same endpoints. This class is only ever listed
    on the download views, never globally.
    """

    def authenticate_header(self, request):
        # Without a challenge DRF answers 403 for every failure on these views, which
        # would report an expired link as a permission problem rather than as a
        # credential the client should replace.
        return 'Download realm="api"'

    def authenticate(self, request):
        query_params = getattr(request, "query_params", None)
        if query_params is None:
            query_params = request.GET

        token = query_params.get("token")

        if not token:
            return None

        try:
            payload = unsign_download_token(token)
        except DownloadTokenExpired:
            raise AuthenticationFailed(
                {
                    "detail": (
                        "The download link has expired. Open the list again to get a "
                        "fresh one."
                    ),
                    "error": "ERROR_DOWNLOAD_TOKEN_EXPIRED",
                }
            )
        except DownloadTokenInvalid:
            # Never log the token itself, only that one failed and where.
            logger.warning(
                "An invalid download token was presented at %s by %s.",
                request.path,
                request.META.get("REMOTE_ADDR", "an unknown address"),
            )
            raise AuthenticationFailed(
                {
                    "detail": "The download link is not valid.",
                    "error": "ERROR_DOWNLOAD_TOKEN_INVALID",
                }
            )

        try:
            user = User.objects.select_related("profile").get(id=payload.user_id)
        except User.DoesNotExist:
            raise AuthenticationFailed(
                {
                    "detail": "The download link is not valid.",
                    "error": "ERROR_DOWNLOAD_TOKEN_INVALID",
                }
            )

        if not user.is_active or user.profile.to_be_deleted:
            raise AuthenticationFailed(
                {
                    "detail": "The user the download link was created for is disabled.",
                    "error": "ERROR_USER_NOT_ACTIVE",
                }
            )

        # The view checks this against its own route, so a token minted for one object
        # cannot be replayed against another.
        request.download_token_payload = payload

        set_user_remote_addr_ip_from_request(user, request)
        with setup_user_in_baggage_and_spans(user, request):
            return user, payload
