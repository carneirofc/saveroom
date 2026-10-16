from django.urls import re_path

from .views import DataDestinationsView

app_name = "baserow.api.data_destinations"

urlpatterns = [
    re_path(r"^$", DataDestinationsView.as_view(), name="list"),
]
