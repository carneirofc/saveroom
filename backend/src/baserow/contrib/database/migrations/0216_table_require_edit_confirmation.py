from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("database", "0215_database_access_grants"),
    ]

    operations = [
        migrations.AddField(
            model_name="table",
            name="require_edit_confirmation",
            field=models.BooleanField(
                db_default=False,
                default=False,
                help_text=(
                    "When enabled, the web frontend stages row edits until the user "
                    "explicitly saves them and asks for confirmation before "
                    "destructive or bulk row operations. This is a UI safeguard only "
                    "and is not enforced by the API."
                ),
            ),
        ),
    ]
