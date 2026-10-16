from django.conf import settings
from django.db import models

from baserow.core.mixins import CreatedAndUpdatedOnMixin

TEAM_MEMBER_SOURCE_MANUAL = "manual"
TEAM_MEMBER_SSO_SOURCE_PREFIX = "sso:"


def sso_team_member_source(provider_id: int) -> str:
    return f"{TEAM_MEMBER_SSO_SOURCE_PREFIX}{provider_id}"


class Team(CreatedAndUpdatedOnMixin, models.Model):
    """
    A named group of workspace members. Teams are subjects of in-app access grants,
    so an admin can tune the access of many members at once.
    """

    workspace = models.ForeignKey(
        "core.Workspace",
        on_delete=models.CASCADE,
        related_name="teams",
        help_text="The workspace this team belongs to.",
    )
    name = models.CharField(max_length=255)

    class Meta:
        ordering = ("name", "id")
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "name"], name="core_team_unique_name"
            )
        ]

    def __str__(self):
        return f"<Team id={self.id}, name={self.name}>"


class TeamMember(CreatedAndUpdatedOnMixin, models.Model):
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="team_memberships",
    )
    source = models.CharField(
        max_length=64,
        default=TEAM_MEMBER_SOURCE_MANUAL,
        help_text="How the membership was created: `manual`, or `sso:<provider id>` "
        "when an OIDC team mapping added it. Only SSO-sourced memberships are ever "
        "revoked by the SSO sync.",
    )

    class Meta:
        ordering = ("id",)
        constraints = [
            models.UniqueConstraint(
                fields=["team", "user"], name="core_team_member_unique"
            )
        ]
