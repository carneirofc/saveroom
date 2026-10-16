from django.urls import re_path

from .views import ApiClientKeysView, ApiClientKeyView, ApiClientsView, ApiClientView

app_name = "baserow.api.api_clients"

urlpatterns = [
    re_path(
        r"^workspace/(?P<workspace_id>[0-9]+)/$",
        ApiClientsView.as_view(),
        name="list",
    ),
    re_path(
        r"^keys/(?P<key_id>[0-9]+)/$",
        ApiClientKeyView.as_view(),
        name="key_item",
    ),
    re_path(
        r"^(?P<client_id>[0-9]+)/keys/$",
        ApiClientKeysView.as_view(),
        name="keys",
    ),
    re_path(
        r"^(?P<client_id>[0-9]+)/$",
        ApiClientView.as_view(),
        name="item",
    ),
]
