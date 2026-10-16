import urllib.parse
from typing import Any, Dict, Optional

from django.conf import settings
from django.urls import reverse

from baserow.core.auth_provider.auth_provider_types import AuthProviderType
from baserow.core.auth_provider.models import OIDCAuthProviderModel
from baserow.core.sso.oidc.config import OIDCProviderConfig, get_oidc_providers

OIDC_PROVIDER_TYPE = "openid_connect"


class OIDCAuthProviderType(AuthProviderType):
    """
    Env-configured OpenID Connect authentication provider.

    Providers are declared in the ``BASEROW_OIDC_PROVIDERS`` environment variable; this
    type exposes one login button per declared provider and drives the
    authorization-code flow through :class:`OIDCHandler`. The database model is only a
    per-provider anchor for the shared user-linkage machinery, so instances cannot be
    created or deleted through the API.
    """

    type = OIDC_PROVIDER_TYPE
    model_class = OIDCAuthProviderModel
    allowed_fields = ["name"]
    serializer_field_names = ["name"]

    def can_create_new_providers(self, **kwargs) -> bool:
        return False

    def can_delete_existing_providers(self) -> bool:
        return False

    @staticmethod
    def _backend_url(url_name: str, config: OIDCProviderConfig) -> str:
        return urllib.parse.urljoin(
            settings.OAUTH_BACKEND_URL,
            reverse(url_name, args=(config.name,)),
        )

    @classmethod
    def get_login_url(cls, config: OIDCProviderConfig) -> str:
        return cls._backend_url("api:sso:oidc:login", config)

    @classmethod
    def get_callback_url(cls, config: OIDCProviderConfig) -> str:
        return cls._backend_url("api:sso:oidc:callback", config)

    @classmethod
    def get_or_create_provider_model(
        cls, config: OIDCProviderConfig
    ) -> OIDCAuthProviderModel:
        """
        Returns the database anchor row for the env-configured provider, creating it on
        first use. The row exists solely to anchor the ``users`` M2M and the
        different-provider guard.
        """

        provider, _ = OIDCAuthProviderModel.objects.get_or_create(name=config.name)
        return provider

    def get_login_options(self, **kwargs) -> Optional[Dict[str, Any]]:
        providers = get_oidc_providers()
        if not providers:
            return None

        items = [
            {
                "type": self.type,
                "name": config.display_name,
                "redirect_url": self.get_login_url(config),
            }
            for config in providers
        ]

        default_redirect_url = items[0]["redirect_url"] if len(items) == 1 else None

        return {
            "type": self.type,
            "items": items,
            "default_redirect_url": default_redirect_url,
        }
