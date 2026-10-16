import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import baserow.core.fields


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0120_backup_destinations"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Team",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_on", models.DateTimeField(auto_now_add=True)),
                (
                    "updated_on",
                    baserow.core.fields.SyncedDateTimeField(auto_now=True),
                ),
                ("name", models.CharField(max_length=255)),
                (
                    "workspace",
                    models.ForeignKey(
                        help_text="The workspace this team belongs to.",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="teams",
                        to="core.workspace",
                    ),
                ),
            ],
            options={"ordering": ("name", "id")},
        ),
        migrations.AddConstraint(
            model_name="team",
            constraint=models.UniqueConstraint(
                fields=("workspace", "name"), name="core_team_unique_name"
            ),
        ),
        migrations.CreateModel(
            name="TeamMember",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_on", models.DateTimeField(auto_now_add=True)),
                (
                    "updated_on",
                    baserow.core.fields.SyncedDateTimeField(auto_now=True),
                ),
                (
                    "source",
                    models.CharField(
                        default="manual",
                        help_text="How the membership was created: `manual`, or "
                        "`sso:<provider id>` when an OIDC team mapping added it. Only "
                        "SSO-sourced memberships are ever revoked by the SSO sync.",
                        max_length=64,
                    ),
                ),
                (
                    "team",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="members",
                        to="core.team",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="team_memberships",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ("id",)},
        ),
        migrations.AddConstraint(
            model_name="teammember",
            constraint=models.UniqueConstraint(
                fields=("team", "user"), name="core_team_member_unique"
            ),
        ),
    ]
