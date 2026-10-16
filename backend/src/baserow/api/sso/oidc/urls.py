from django.urls import re_path

from baserow.api.sso.oidc.views import OIDCCallbackView, OIDCLoginView

app_name = "baserow.api.sso.oidc"

urlpatterns = [
    re_path(
        r"^login/(?P<provider_name>[a-zA-Z0-9_-]+)/$",
        OIDCLoginView.as_view(),
        name="login",
    ),
    re_path(
        r"^callback/(?P<provider_name>[a-zA-Z0-9_-]+)/$",
        OIDCCallbackView.as_view(),
        name="callback",
    ),
]
