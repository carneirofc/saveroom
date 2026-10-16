from django.urls import re_path

from .views import DatabaseAccessView

app_name = "baserow.contrib.database.api.access"

urlpatterns = [
    re_path(
        r"(?P<scope_type>workspace|database|table)/(?P<scope_id>[0-9]+)/$",
        DatabaseAccessView.as_view(),
        name="item",
    ),
]
