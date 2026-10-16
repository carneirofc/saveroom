from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0116_oidcssoworkspacemembership"),
    ]

    operations = [
        migrations.AddField(
            model_name="settings",
            name="enable_database",
            field=models.BooleanField(
                db_default=True,
                default=True,
                help_text="Indicates whether database applications can be created.",
            ),
        ),
        migrations.AddField(
            model_name="settings",
            name="enable_builder",
            field=models.BooleanField(
                db_default=True,
                default=True,
                help_text="Indicates whether builder applications can be created.",
            ),
        ),
        migrations.AddField(
            model_name="settings",
            name="enable_automation",
            field=models.BooleanField(
                db_default=True,
                default=True,
                help_text="Indicates whether automation applications can be created.",
            ),
        ),
        migrations.AddField(
            model_name="settings",
            name="enable_dashboard",
            field=models.BooleanField(
                db_default=True,
                default=True,
                help_text="Indicates whether dashboard applications can be created.",
            ),
        ),
    ]
