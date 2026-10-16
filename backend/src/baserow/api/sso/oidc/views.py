from datetime import timedelta
from typing import Any, Dict

from django.db import transaction
from django.http import HttpResponseRedirect
from django.shortcuts import redirect

from drf_spectacular.openapi import OpenApiParameter, OpenApiTypes
from drf_spectacular.utils import extend_schema
from loguru import logger
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.views import APIView

from baserow.api.decorators import validate_query_parameters
from baserow.api.sso.oidc.serializers import OIDCLoginRequestSerializer
from baserow.core.auth_provider.exceptions import DifferentAuthProvider
from baserow.core.sso.exceptions import (
    AuthFlowError,
    EmailNotVerified,
    NoMappedRole,
    OIDCProviderNotFound,
)
from baserow.core.sso.oidc.config import get_oidc_provider
from baserow.core.sso.oidc.handler import OIDCHandler
from baserow.core.sso.oidc.linking import link_existing_account
from baserow.core.sso.oidc.provider import OIDCAuthProviderType
from baserow.core.sso.oidc.roles import enforce_role_access, sync_global_roles
from baserow.core.sso.utils import (
    SsoErrorCode,
    map_sso_exceptions,
    redirect_to_sign_in_error_page,
    redirect_user_on_success,
)
from baserow.core.user.exceptions import DeactivatedUserException, DisabledSignupError


class OIDCLoginView(APIView):
    permission_classes = (AllowAny,)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="provider_name",
                location=OpenApiParameter.PATH,
                type=OpenApiTypes.STR,
                description="The name of the env-configured OIDC provider.",
            ),
            OpenApiParameter(
                name="original",
                location=OpenApiParameter.QUERY,
                type=OpenApiTypes.STR,
                description="The relative URL the user wanted to access.",
            ),
        ],
        tags=["Auth"],
        operation_id="oidc_login_redirect",
        description=(
            "Redirects to the OpenID Connect provider's authorization URL to start "
            "the login flow."
        ),
        responses={302: None},
        auth=[],
    )
    @validate_query_parameters(OIDCLoginRequestSerializer, return_validated=True)
    @map_sso_exceptions(
        {
            OIDCProviderNotFound: SsoErrorCode.PROVIDER_DOES_NOT_EXIST,
            AuthFlowError: SsoErrorCode.AUTH_FLOW_ERROR,
        }
    )
    def get(
        self, request: Request, provider_name: str, query_params: Dict[str, Any]
    ) -> HttpResponseRedirect:
        config = get_oidc_provider(provider_name)
        if config is None:
            raise OIDCProviderNotFound()

        authorization_url = OIDCHandler.get_authorization_redirect_url(
            config,
            OIDCAuthProviderType.get_callback_url(config),
            request.session,
            query_params,
        )
        return redirect(authorization_url)


class OIDCCallbackView(APIView):
    permission_classes = (AllowAny,)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="provider_name",
                location=OpenApiParameter.PATH,
                type=OpenApiTypes.STR,
                description="The name of the env-configured OIDC provider.",
            ),
            OpenApiParameter(
                name="code",
                location=OpenApiParameter.QUERY,
                type=OpenApiTypes.STR,
                description="The authorization code returned by the provider.",
            ),
        ],
        tags=["Auth"],
        operation_id="oidc_login_callback",
        description=(
            "Processes the callback from the OpenID Connect provider and logs the user "
            "in if successful."
        ),
        responses={302: None},
        auth=[],
    )
    @map_sso_exceptions(
        {
            OIDCProviderNotFound: SsoErrorCode.PROVIDER_DOES_NOT_EXIST,
            AuthFlowError: SsoErrorCode.AUTH_FLOW_ERROR,
            DeactivatedUserException: SsoErrorCode.USER_DEACTIVATED,
            DifferentAuthProvider: SsoErrorCode.DIFFERENT_PROVIDER,
            DisabledSignupError: SsoErrorCode.SIGNUP_DISABLED,
            NoMappedRole: SsoErrorCode.NO_MAPPED_ROLE,
            EmailNotVerified: SsoErrorCode.EMAIL_NOT_VERIFIED,
        }
    )
    @transaction.atomic
    def get(self, request: Request, provider_name: str) -> HttpResponseRedirect:
        config = get_oidc_provider(provider_name)
        if config is None:
            raise OIDCProviderNotFound()

        code = request.query_params.get("code", None)
        if not code:
            return redirect_to_sign_in_error_page(SsoErrorCode.AUTH_FLOW_ERROR)

        user_info, original_url, roles = OIDCHandler.get_user_info(
            config,
            OIDCAuthProviderType.get_callback_url(config),
            code,
            request.query_params.get("state", None),
            request.session,
        )
        logger.debug("OIDC extracted user info: {0}", user_info)

        try:
            # Refuse before anything is written, so a user without a mapped client role
            # is never provisioned an account.
            enforce_role_access(config, roles)
        except NoMappedRole:
            logger.warning(
                "Refusing the OIDC login of '{0}' through provider '{1}': none of "
                "their roles {2} are mapped to access.",
                user_info.email,
                config.name,
                roles,
            )
            raise

        provider = OIDCAuthProviderType().get_or_create_provider_model(config)
        # Runs inside the transaction, so a refusal further down undoes the link.
        link_existing_account(config, provider, user_info)
        user, _ = provider.get_type().get_or_create_user_and_sign_in(
            provider, user_info
        )

        # The IdP only defines global profiles; workspace access is managed in the app.
        sync_global_roles(user, roles, config)

        # Bounding the session is what makes a client role removed in the IdP stop
        # applying: the next sign-in re-runs the syncs above.
        refresh_lifetime = (
            timedelta(minutes=config.session_lifetime_minutes)
            if config.session_lifetime_minutes is not None
            else None
        )
        return redirect_user_on_success(user, original_url, refresh_lifetime)
