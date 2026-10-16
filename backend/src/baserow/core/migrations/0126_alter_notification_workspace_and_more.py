import django.db.models.deletion
from django.db import migrations, models

SUPPORTED_LANGUAGES = ["en", "pt-BR"]


def reset_unsupported_languages(apps, schema_editor):
    UserProfile = apps.get_model("core", "UserProfile")
    UserProfile.objects.exclude(language__in=SUPPORTED_LANGUAGES).update(language="en")


class Migration(migrations.Migration):
    """
    The interface now ships English and Brazilian Portuguese only, so profiles set to
    a language that is no longer available fall back to English.
    """

    dependencies = [
        ("core", "0125_remove_workspace_invitations"),
    ]

    operations = [
        migrations.AlterField(
            model_name="notification",
            name="workspace",
            field=models.ForeignKey(
                help_text="The workspace where the notification lives.If the notification is a broadcast notification, then the workspace will be None.Workspace can be null also if the notification is not associated with a specific workspace.",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="notifications",
                to="core.workspace",
            ),
        ),
        migrations.AlterField(
            model_name="userprofile",
            name="language",
            field=models.TextField(
                choices=[("en", "English"), ("pt-BR", "Portuguese (Brazil)")],
                default="en",
                help_text="An ISO 639 language code (with optional variant) selected by the user. Ex: en-GB.",
                max_length=10,
            ),
        ),
        migrations.RunPython(
            reset_unsupported_languages, migrations.RunPython.noop, elidable=True
        ),
    ]
