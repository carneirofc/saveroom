from django.conf import settings

from .registries import EmailContextType


class CoreEmailContextType(EmailContextType):
    """
    An `EmailContextType` represents a context in which an email can be sent.
    """

    type = "core"

    def get_context(self):
        return {
            "public_backend_hostname": settings.PUBLIC_BACKEND_HOSTNAME,
            "public_backend_url": settings.PUBLIC_BACKEND_URL,
            "public_web_frontend_hostname": settings.PUBLIC_WEB_FRONTEND_HOSTNAME,
            "public_web_frontend_url": settings.PUBLIC_WEB_FRONTEND_URL,
            "baserow_embedded_share_url": settings.BASEROW_EMBEDDED_SHARE_URL,
            "baserow_embedded_share_hostname": settings.BASEROW_EMBEDDED_SHARE_HOSTNAME,
            "app_name": settings.BRANDING_APP_NAME,
            # Served by the web-frontend's branding route, so a logo replaced
            # through runtime branding reaches the emails too.
            "logo_url": settings.PUBLIC_WEB_FRONTEND_URL
            + "/_branding/assets/img/logo.svg",
            "logo_additional_text": "",
        }
