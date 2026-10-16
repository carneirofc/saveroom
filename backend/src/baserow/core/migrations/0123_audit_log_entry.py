import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0122_remove_granular_roles_and_sso_memberships"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AuditLogEntry",
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
                (
                    "user_email",
                    models.CharField(blank=True, default="", max_length=254),
                ),
                (
                    "ip_address",
                    models.GenericIPAddressField(blank=True, null=True),
                ),
                (
                    "action_type",
                    models.CharField(db_index=True, max_length=100),
                ),
                (
                    "command_type",
                    models.CharField(
                        choices=[
                            ("DO", "DO"),
                            ("UNDO", "UNDO"),
                            ("REDO", "REDO"),
                            ("AUTH", "AUTH"),
                        ],
                        max_length=10,
                    ),
                ),
                ("description", models.TextField(blank=True, default="")),
                ("data", models.JSONField(blank=True, default=dict)),
                ("created_on", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "workspace",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="core.workspace",
                    ),
                ),
            ],
            options={"ordering": ("-created_on",)},
        ),
        migrations.AddIndex(
            model_name="auditlogentry",
            index=models.Index(
                fields=["-created_on"], name="core_auditl_created_9c5e8b_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="auditlogentry",
            index=models.Index(fields=["user"], name="core_auditl_user_id_1f2a3c_idx"),
        ),
        migrations.AddIndex(
            model_name="auditlogentry",
            index=models.Index(
                fields=["workspace"], name="core_auditl_workspa_4d6b7e_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="auditlogentry",
            index=models.Index(
                fields=["action_type"], name="core_auditl_action__8a1f2d_idx"
            ),
        ),
    ]
