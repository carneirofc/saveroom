"""
Linking of existing Baserow accounts to an env-configured OIDC provider.

Accounts are refused by the different-provider guard when they were created through
another authentication method. A provider that opts in with `link_existing_accounts`
links such an account on sign-in instead, but only when the IdP explicitly verifies the
email and never for staff or superusers: those are linked by an operator through the
`link_oidc_account` management command.
"""

from loguru import logger

from baserow.core.auth_provider.models import OIDCAuthProviderModel
from baserow.core.auth_provider.types import UserInfo
from baserow.core.sso.oidc.config import OIDCProviderConfig
from baserow.core.user.exceptions import UserNotFound


def link_existing_account(
    config: OIDCProviderConfig,
    provider: OIDCAuthProviderModel,
    user_info: UserInfo,
) -> bool:
    """
    Links the existing active account matching the user info's email to the provider,
    when the provider allows it.

    :param config: The provider configuration.
    :param provider: The provider's database anchor row.
    :param user_info: The user info extracted from the identity provider.
    :return: True if a new link was created, False otherwise.
    """

    from baserow.core.user.handler import UserHandler

    if not config.link_existing_accounts or user_info.email_verified is not True:
        return False

    try:
        user = UserHandler().get_active_user(email=user_info.email)
    except UserNotFound:
        return False

    if provider.users.filter(id=user.id).exists():
        return False

    if user.is_staff or user.is_superuser:
        logger.warning(
            "Not linking the privileged account '{0}' to OIDC provider '{1}'; link it "
            "with the `link_oidc_account` management command instead.",
            user.email,
            config.name,
        )
        return False

    provider.users.add(user)
    logger.info(
        "Linked the existing account '{0}' to OIDC provider '{1}'.",
        user.email,
        config.name,
    )
    return True
