from django.urls import re_path

from baserow.api.admin.limits.views import AdminOperationalLimitsView

app_name = "baserow.api.admin.limits"

urlpatterns = [
    re_path(r"^$", AdminOperationalLimitsView.as_view(), name="limits"),
]
