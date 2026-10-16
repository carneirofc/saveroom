from django.conf import settings
from django.db import models
from django.db.models import Q

from baserow.core.mixins import CreatedAndUpdatedOnMixin

ACCESS_LEVEL_NONE = "none"
ACCESS_LEVEL_VIEWER = "viewer"
ACCESS_LEVEL_EDITOR = "editor"
ACCESS_LEVEL_BUILDER = "builder"

# Ordered from least to most access.
ACCESS_LEVELS = [
    ACCESS_LEVEL_NONE,
    ACCESS_LEVEL_VIEWER,
    ACCESS_LEVEL_EDITOR,
    ACCESS_LEVEL_BUILDER,
]
ACCESS_LEVEL_CHOICES = [(level, level) for level in ACCESS_LEVELS]

_SCOPES = {
    "workspace": Q(database__isnull=True, table__isnull=True),
    "database": Q(database__isnull=False, table__isnull=True),
    "table": Q(database__isnull=True, table__isnull=False),
}
_SUBJECTS = {
    "user": Q(user__isnull=False, team__isnull=True),
    "team": Q(user__isnull=True, team__isnull=False),
}


def _unique_constraints():
    constraints = []
    for scope_name, scope_q in _SCOPES.items():
        scope_fields = {
            "workspace": ["workspace"],
            "database": ["database"],
            "table": ["table"],
        }[scope_name]
        for subject_name, subject_q in _SUBJECTS.items():
            constraints.append(
                models.UniqueConstraint(
                    fields=[*scope_fields, subject_name],
                    condition=scope_q & subject_q,
                    name=f"db_access_grant_unique_{scope_name}_{subject_name}",
                )
            )
    return constraints


class DatabaseAccessGrant(CreatedAndUpdatedOnMixin, models.Model):
    """
    An in-app access level given to a workspace member or a team for the whole
    workspace (default), one database or one table. The most specific scope with a
    grant decides a member's access; see `resolver.py`.
    """

    workspace = models.ForeignKey(
        "core.Workspace",
        on_delete=models.CASCADE,
        related_name="database_access_grants",
    )
    database = models.ForeignKey(
        "database.Database",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="access_grants",
    )
    table = models.ForeignKey(
        "database.Table",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="access_grants",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="database_access_grants",
    )
    team = models.ForeignKey(
        "core.Team",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="database_access_grants",
    )
    level = models.CharField(max_length=16, choices=ACCESS_LEVEL_CHOICES)

    class Meta:
        ordering = ("id",)
        constraints = [
            models.CheckConstraint(
                condition=_SUBJECTS["user"] | _SUBJECTS["team"],
                name="db_access_grant_one_subject",
            ),
            models.CheckConstraint(
                condition=~Q(database__isnull=False, table__isnull=False),
                name="db_access_grant_one_scope",
            ),
            *_unique_constraints(),
        ]

    @property
    def scope_type(self) -> str:
        if self.table_id is not None:
            return "table"
        if self.database_id is not None:
            return "database"
        return "workspace"

    @property
    def subject_type(self) -> str:
        return "team" if self.team_id is not None else "user"
