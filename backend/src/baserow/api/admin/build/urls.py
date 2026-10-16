from django.urls import re_path

from baserow.api.admin.build.views import AdminBuildInfoView

app_name = "baserow.api.admin.build"

urlpatterns = [
    re_path(r"^$", AdminBuildInfoView.as_view(), name="build"),
]
