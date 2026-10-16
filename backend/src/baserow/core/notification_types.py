from loguru import logger

from baserow.core.notifications.handler import NotificationHandler
from baserow.core.notifications.registries import (
    CliNotificationTypeMixin,
    NotificationType,
)


class BaserowVersionUpgradeNotificationType(CliNotificationTypeMixin, NotificationType):
    type = "baserow_version_upgrade"

    @classmethod
    def create_version_upgrade_broadcast_notification(
        cls, version, release_notes_url=None
    ):
        NotificationHandler.create_broadcast_notification(
            notification_type=cls.type,
            sender=None,
            data={"version": version, "release_notes_url": release_notes_url},
        )

    @classmethod
    def prompt_for_args_in_cli_and_create_notification(cls):
        version = input("Enter the version number (i.e. 1.19): ")
        if not version:
            print("Version is required.")
            return

        release_notes_url = input(
            "Enter the release notes URL (i.e. https://github.com/carneirofc/baserow/releases/tag/1.19): "
        )

        confirm = input(
            "Are you sure you want to create a notification with these data?\n\n"
            f"Version: {version}\n"
            f"Release notes URL: {release_notes_url}\n\n"
            "Enter 'y' to confirm: "
        )
        if confirm.lower() == "y":
            cls.create_version_upgrade_broadcast_notification(
                version, release_notes_url
            )
            logger.info(
                f"Broadcast notification {cls.type} successfully created via CLI."
            )
