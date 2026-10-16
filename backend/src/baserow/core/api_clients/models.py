from django.contrib.auth import get_user_model
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.utils import timezone

from baserow.core.mixins import (
    CreatedAndUpdatedOnMixin,
    HierarchicalModelMixin,
    ParentWorkspaceTrashableModelMixin,
)
from baserow.core.models import Workspace

User = get_user_model()


class ApiClient(
    CreatedAndUpdatedOnMixin,
    HierarchicalModelMixin,
    ParentWorkspaceTrashableModelMixin,
    models.Model,
):
    """
    An API client represents an external, non human integration that talks to Baserow
    on behalf of the user that created it. It is limited to a single workspace and to
    the scopes it was granted. Authentication happens through one of its keys.
    """

    name = models.CharField(
        max_length=100,
        help_text="The human readable name of the API client.",
    )
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name="api_clients",
        help_text="Only the resources of this workspace can be accessed.",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        help_text=(
            "The user that owns the API client. Requests made with one of the "
            "client's keys are performed on behalf of this user."
        ),
    )
    scopes = ArrayField(
        base_field=models.CharField(max_length=64),
        default=list,
        help_text="The scopes that requests made with this client are limited to.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text=(
            "If false, every key of this client is rejected without being deleted."
        ),
    )

    class Meta:
        ordering = ("id",)

    def get_parent(self):
        return self.workspace


class ApiClientKey(models.Model):
    """
    A single credential of an API client. Only a hash of the secret is stored, so the
    plain secret can be shown exactly once, right after creation.
    """

    api_client = models.ForeignKey(
        ApiClient,
        on_delete=models.CASCADE,
        related_name="keys",
        help_text="The API client this key authenticates as.",
    )
    name = models.CharField(
        max_length=100,
        blank=True,
        help_text="An optional label, useful when a client has multiple keys.",
    )
    prefix = models.CharField(
        max_length=8,
        unique=True,
        db_index=True,
        help_text=(
            "The public, non secret part of the key. Used to look up the key before "
            "verifying the secret."
        ),
    )
    hashed_secret = models.CharField(
        max_length=128,
        help_text="The hash of the secret part of the key.",
    )
    created_on = models.DateTimeField(auto_now_add=True)
    last_used_on = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this key was last used to authenticate a request.",
    )
    expires_on = models.DateTimeField(
        null=True,
        blank=True,
        help_text="After this moment the key is rejected. Null means it never expires.",
    )
    revoked_on = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When set, the key is rejected.",
    )

    class Meta:
        ordering = ("id",)

    @property
    def is_usable(self) -> bool:
        if self.revoked_on is not None:
            return False
        if self.expires_on is not None and self.expires_on <= timezone.now():
            return False
        return True
