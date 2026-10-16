from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework import HTTP_HEADER_ENCODING
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import BasePermission

from baserow.api.sessions import set_user_remote_addr_ip_from_request
from baserow.core.api_clients.exceptions import ApiClientKeyDoesNotExist
from baserow.core.api_clients.handler import ApiClientHandler
from baserow.core.telemetry.utils import setup_user_in_baggage_and_spans


class ApiClientAuthentication(BaseAuthentication):
    """
    Authenticates a request made with an API client key.

    The expected header is `Authorization: Client <prefix>.<secret>`. Any other scheme
    is left alone so that JWT authentication keeps working on the same endpoints.
    """

    def authenticate(self, request):
        auth = get_authorization_header(request).split()

        if not auth or auth[0].lower() != b"client":
            return None

        if len(auth) == 1:
            raise AuthenticationFailed(
                {
                    "detail": "Invalid client header. No key provided.",
                    "error": "ERROR_INVALID_API_CLIENT_HEADER",
                }
            )
        elif len(auth) > 2:
            raise AuthenticationFailed(
                {
                    "detail": "Invalid client header. Key should not contain spaces.",
                    "error": "ERROR_INVALID_API_CLIENT_HEADER",
                }
            )

        raw_key = auth[1].decode(HTTP_HEADER_ENCODING)

        try:
            api_client = ApiClientHandler().authenticate(raw_key)
        except ApiClientKeyDoesNotExist:
            raise AuthenticationFailed(
                {
                    "detail": "The provided API client key is invalid.",
                    "error": "ERROR_INVALID_API_CLIENT_KEY",
                }
            )

        user = api_client.user

        if not user.is_active:
            raise AuthenticationFailed(
                {
                    "detail": "The user related to the API client is disabled.",
                    "error": "ERROR_USER_NOT_ACTIVE",
                }
            )

        request.api_client = api_client
        set_user_remote_addr_ip_from_request(user, request)
        with setup_user_in_baggage_and_spans(user, request):
            return user, api_client


class HasApiClientScope(BasePermission):
    """
    Requires a scope when the request was authenticated with an API client key.

    A request made by a signed in user is unaffected: the regular permission managers
    already decide what that user may do. Scopes exist only to narrow down what a
    machine credential of that same user is allowed to reach.

    The view declares what it needs through `api_client_scopes`, either a single scope
    for every method or a mapping of HTTP method to scope::

        class BackupView(APIView):
            permission_classes = (IsAuthenticated, HasApiClientScope)
            api_client_scopes = {"GET": "backup.read", "DELETE": "backup.write"}

    A method that is not in the mapping is refused for API clients, so forgetting to
    declare a scope fails closed. A scope value may also be a tuple of scopes, in which
    case the client needs every one of them.

    An API client is bound to the workspace it was created in. The workspace of the
    request is taken from `view.get_api_client_workspace_id(request, **view.kwargs)`
    when the view defines it, otherwise from the `workspace_id` url kwarg. A request
    whose workspace cannot be resolved, or differs from the client's, is refused. A view
    that is not about a workspace at all sets `api_client_workspace_independent = True`.
    """

    message = "The API client does not have the scope required for this endpoint."

    def has_permission(self, request, view):
        api_client = getattr(request, "api_client", None)

        if api_client is None:
            return True

        required = getattr(view, "api_client_scopes", None)

        if isinstance(required, (str, tuple)):
            scope = required
        elif isinstance(required, dict):
            scope = required.get(request.method)
        else:
            scope = None

        if scope is None:
            return False

        scopes = (scope,) if isinstance(scope, str) else tuple(scope)
        if not all(item in api_client.scopes for item in scopes):
            return False

        if getattr(view, "api_client_workspace_independent", False):
            return True

        return self._get_workspace_id(request, view) == api_client.workspace_id

    @staticmethod
    def _get_workspace_id(request, view):
        kwargs = getattr(view, "kwargs", None) or {}
        resolver = getattr(view, "get_api_client_workspace_id", None)

        try:
            if resolver is not None:
                workspace_id = resolver(request, **kwargs)
            else:
                workspace_id = kwargs.get("workspace_id")
            return None if workspace_id is None else int(workspace_id)
        except TypeError, ValueError:
            return None


class ApiClientAuthenticationExtension(OpenApiAuthenticationExtension):
    target_class = "baserow.api.api_clients.authentication.ApiClientAuthentication"
    name = "API client key"
    match_subclasses = True
    priority = -1

    def get_security_definition(self, auto_schema):
        return {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "Client your_api_client_key",
        }
