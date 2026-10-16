import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.db.models import Q

import baserow.core.fields

_SCOPES = {
    "workspace": (["workspace"], Q(database__isnull=True, table__isnull=True)),
    "database": (["database"], Q(database__isnull=False, table__isnull=True)),
    "table": (["table"], Q(database__isnull=True, table__isnull=False)),
}
_SUBJECTS = {
    "user": Q(user__isnull=False, team__isnull=True),
    "team": Q(user__isnull=True, team__isnull=False),
}


def _unique_constraints():
    return [
        migrations.AddConstraint(
            model_name="databaseaccessgrant",
            constraint=models.UniqueConstraint(
                fields=[*scope_fields, subject_name],
                condition=scope_q & subject_q,
                name=f"db_access_grant_unique_{scope_name}_{subject_name}",
            ),
        )
        for scope_name, (scope_fields, scope_q) in _SCOPES.items()
        for subject_name, subject_q in _SUBJECTS.items()
    ]


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0121_teams"),
        ("database", "0214_table_export_schedules"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="DatabaseAccessGrant",
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
                    "level",
                    models.CharField(
                        choices=[
                            ("none", "none"),
                            ("viewer", "viewer"),
                            ("editor", "editor"),
                            ("builder", "builder"),
                        ],
                        max_length=16,
                    ),
                ),
                (
                    "database",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="access_grants",
                        to="database.database",
                    ),
                ),
                (
                    "table",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="access_grants",
                        to="database.table",
                    ),
                ),
                (
                    "team",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="database_access_grants",
                        to="core.team",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="database_access_grants",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "workspace",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="database_access_grants",
                        to="core.workspace",
                    ),
                ),
            ],
            options={"ordering": ("id",)},
        ),
        migrations.AddConstraint(
            model_name="databaseaccessgrant",
            constraint=models.CheckConstraint(
                condition=Q(user__isnull=False, team__isnull=True)
                | Q(user__isnull=True, team__isnull=False),
                name="db_access_grant_one_subject",
            ),
        ),
        migrations.AddConstraint(
            model_name="databaseaccessgrant",
            constraint=models.CheckConstraint(
                condition=~Q(database__isnull=False, table__isnull=False),
                name="db_access_grant_one_scope",
            ),
        ),
        *_unique_constraints(),
    ]
