from django.urls import include, path

from baserow.api.sso.oidc import urls as oidc_urls

app_name = "baserow.api.sso"

urlpatterns = [
    path("oidc/", include(oidc_urls, namespace="oidc")),
]
