from baserow.core.backups.models import BackupSchedule
from baserow.core.backups.schedule_handler import BackupScheduleHandler


class BackupFixtures:
    def create_backup_schedule(self, **kwargs):
        if "name" not in kwargs:
            kwargs["name"] = self.fake.name()

        if "user" not in kwargs:
            kwargs["user"] = self.create_user()

        if "workspace" not in kwargs:
            kwargs["workspace"] = self.create_workspace(user=kwargs["user"])

        if "cron" not in kwargs:
            kwargs["cron"] = "0 3 * * *"

        if "next_run_on" not in kwargs:
            kwargs["next_run_on"] = BackupScheduleHandler().compute_next_run_on(
                kwargs["cron"], kwargs.get("timezone", "UTC")
            )

        return BackupSchedule.objects.create(**kwargs)
