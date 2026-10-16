from typing import Any, Dict, Iterable, List

from django.conf import settings
from django.contrib.auth.models import AbstractUser

from baserow.core.db import specific_iterator
from baserow.core.handler import CoreHandler
from baserow.core.models import Application, Workspace
from baserow.core.operations import (
    ListApplicationsWorkspaceOperationType,
    ReadApplicationOperationType,
)
from baserow.core.registries import ImportExportConfig, application_type_registry

from .exceptions import ContentsTooLarge


class ContentsHandler:
    """
    Serves the complete contents of a workspace or an application as plain JSON.

    This reuses the very same `export_serialized` implementations the backup archives
    are built from, but without a zip file. That means user files are referenced by
    name rather than embedded, so the result is a faithful read of the data, not a
    restorable artifact. Use a backup when you need to restore.
    """

    def get_import_export_config(self, only_structure: bool) -> ImportExportConfig:
        return ImportExportConfig(
            include_permission_data=False,
            reduce_disk_space_usage=False,
            only_structure=only_structure,
        )

    def get_workspace_applications(
        self, user: AbstractUser, workspace: Workspace
    ) -> List[Application]:
        """
        Returns the applications of a workspace the user is allowed to read.

        :param user: The user on whose behalf the applications are read.
        :param workspace: The workspace to read.
        :return: The specific application instances.
        """

        applications = Application.objects.filter(
            workspace=workspace, workspace__trashed=False
        ).select_related("content_type", "workspace")

        applications = CoreHandler().filter_queryset(
            user,
            ListApplicationsWorkspaceOperationType.type,
            applications,
            workspace=workspace,
        )

        return list(specific_iterator(applications))

    def get_workspace_contents(
        self, user: AbstractUser, workspace_id: int, exclude_data: bool = False
    ) -> Dict[str, Any]:
        """
        Serializes every application of a workspace the user may read.

        :param user: The user on whose behalf the contents are read.
        :param workspace_id: The workspace to read.
        :param exclude_data: When true only the structure is returned, without rows.
        :raises ContentsTooLarge: When the contents exceed
            `BASEROW_CONTENTS_API_MAX_ROWS`.
        :return: A JSON serializable dict.
        """

        workspace = CoreHandler().get_workspace(workspace_id)
        CoreHandler().check_permissions(
            user,
            ListApplicationsWorkspaceOperationType.type,
            workspace=workspace,
            context=workspace,
        )

        applications = self.get_workspace_applications(user, workspace)

        if not exclude_data:
            self.raise_if_too_large(applications)

        return {
            "id": workspace.id,
            "name": workspace.name,
            "exclude_data": exclude_data,
            "applications": self._serialize_applications(applications, exclude_data),
        }

    def get_application_contents(
        self, user: AbstractUser, application_id: int, exclude_data: bool = False
    ) -> Dict[str, Any]:
        """
        Serializes a single application.

        :param user: The user on whose behalf the contents are read.
        :param application_id: The application to read.
        :param exclude_data: When true only the structure is returned, without rows.
        :raises ContentsTooLarge: When the contents exceed
            `BASEROW_CONTENTS_API_MAX_ROWS`.
        :return: A JSON serializable dict.
        """

        application = CoreHandler().get_application(application_id)
        CoreHandler().check_permissions(
            user,
            ReadApplicationOperationType.type,
            workspace=application.workspace,
            context=application,
        )

        application = application.specific

        if not exclude_data:
            self.raise_if_too_large([application])

        return {
            "id": application.workspace_id,
            "name": application.workspace.name,
            "exclude_data": exclude_data,
            "applications": self._serialize_applications([application], exclude_data),
        }

    def count_rows(self, applications: Iterable[Application]) -> int:
        """
        Counts the rows the given applications hold.

        Application types without row data simply contribute nothing.

        :param applications: The specific application instances to count.
        :return: The total number of rows.
        """

        # Imported lazily because `baserow.core` must not depend on a contrib app at
        # import time.
        from baserow.contrib.database.models import Database

        total = 0

        for application in applications:
            if not isinstance(application, Database):
                continue

            for table in application.table_set.filter(trashed=False):
                total += table.get_model().objects.count()

        return total

    def raise_if_too_large(self, applications: Iterable[Application]):
        """
        Rejects the request when the applications hold more rows than may be returned
        in one synchronous response.

        :param applications: The specific application instances to check.
        :raises ContentsTooLarge: When the limit is exceeded.
        """

        maximum = settings.BASEROW_CONTENTS_API_MAX_ROWS

        if not maximum:
            return

        row_count = self.count_rows(applications)

        if row_count > maximum:
            raise ContentsTooLarge(row_count, maximum)

    def _serialize_applications(
        self, applications: Iterable[Application], exclude_data: bool
    ) -> List[Dict[str, Any]]:
        import_export_config = self.get_import_export_config(exclude_data)
        serialized = []

        for application in applications:
            application_type = application_type_registry.get_by_model(application)

            # Deliberately not wrapped in `export_safe_transaction_context`. That
            # context switches the transaction to repeatable read, which Postgres only
            # accepts as the very first statement of a transaction and therefore
            # cannot be done from inside a request. Reads here are consistent per
            # statement but not across the whole response, which is why a backup, not
            # this endpoint, is the thing to restore from.
            serialized.append(
                application_type.export_serialized(
                    application,
                    import_export_config,
                    # Without a zip file the user files are referenced instead of
                    # embedded, which is what we want for a JSON read.
                    files_zip=None,
                    storage=None,
                )
            )

        return serialized
