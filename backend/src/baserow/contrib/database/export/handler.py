import uuid
from datetime import datetime, timedelta, timezone
from os.path import join
from typing import Any, Dict, Optional

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction

from loguru import logger

from baserow.contrib.database.export.models import (
    EXPORT_JOB_CANCELLED_STATUS,
    EXPORT_JOB_EXPIRED_STATUS,
    EXPORT_JOB_EXPORTING_STATUS,
    EXPORT_JOB_FAILED_STATUS,
    EXPORT_JOB_FINISHED_STATUS,
    EXPORT_JOB_PENDING_STATUS,
    ExportJob,
)
from baserow.contrib.database.export.operations import ExportTableOperationType
from baserow.contrib.database.export.tasks import run_export_job
from baserow.contrib.database.fields.field_sortings import serialize_sorts_to_string
from baserow.contrib.database.table.models import Table
from baserow.contrib.database.views.exceptions import ViewNotInTable
from baserow.contrib.database.views.filters import AdHocFilters
from baserow.contrib.database.views.models import View
from baserow.contrib.database.views.registries import view_type_registry
from baserow.core import storage as core_storage
from baserow.core.handler import CoreHandler
from baserow.core.storage import (
    _create_storage_dir_if_missing_and_open,
    get_default_storage,
    get_storage_backend_description,
)

from .exceptions import (
    ExportJobCanceledException,
    ExportJobFileNotWrittenException,
    TableOnlyExportUnsupported,
    ViewUnsupportedForExporterType,
)
from .file_writer import PaginatedExportJobFileWriter
from .registries import TableExporter, table_exporter_registry
from .utils import view_is_publicly_exportable

User = get_user_model()


class ExportHandler:
    @staticmethod
    def _raise_if_no_export_permissions(
        user: Optional[User], table: Table, view: Optional[View]
    ):
        if view_is_publicly_exportable(user, view):
            # No need to do the permission check if no user is provided, the view is
            # public, and allowed to export from publicly shared view because this
            # can be initiated by an anonymous user.
            pass
        else:
            CoreHandler().check_permissions(
                user,
                ExportTableOperationType.type,
                workspace=table.database.workspace,
                context=table,
            )

    @staticmethod
    def create_and_start_new_job(
        user: Optional[User],
        table: Table,
        view: Optional[View],
        export_options: Dict[str, Any],
    ) -> ExportJob:
        """
        For the provided user, table, optional view and options will create a new
        export job and start an asynchronous celery task which will perform the
        export and update the job with any results.

        :param user: The user who the export job is being run for.
        :param table: The table on which the job is being run.
        :param view: An optional view of the table to export instead of the table
            itself.
        :param export_options: A dict containing exporter_type and the relevant options
            for that type.
        :return: The created export job.
        """

        job = ExportHandler.create_pending_export_job(user, table, view, export_options)
        # Ensure we only trigger the job after the transaction we are in has committed
        # and created the export job in the database. Otherwise the job might run before
        # we commit and crash as there is no job yet.
        transaction.on_commit(lambda: run_export_job.delay(job.id))
        return job

    @staticmethod
    def create_pending_export_job(
        user: Optional[User],
        table: Table,
        view: Optional[View],
        export_options: Dict[str, Any],
    ):
        """
        Creates a new pending export job configured with the providing options but does
        not start the job. Will cancel any previously running jobs for this user. Raises
        exceptions if the user is not allowed to create an export job for the view/table
        due to missing permissions or if the selected exporter doesn't support the
        view/table.

        :param user: The user who the export job is being run for.
        :param table: The table on which the job is being run.
        :param view: An optional view of the table to export instead of the table
            itself.
        :param export_options: A dict containing exporter_type and the relevant options
            for that type.
        :raises ViewNotInTable: If the view does not belong to the table.
        :return: The created export job.
        """

        exporter_type = export_options.pop("exporter_type")
        exporter = table_exporter_registry.get(exporter_type)
        exporter.before_job_create(user, table, view, export_options)

        ExportHandler._raise_if_no_export_permissions(user, table, view)

        if view and view.table.id != table.id:
            raise ViewNotInTable()

        _cancel_unfinished_jobs(user)

        _raise_if_invalid_view_or_table_for_exporter(exporter_type, view)
        _raise_if_invalid_order_by_or_filters(table, view, export_options)

        job = ExportJob.objects.create(
            user=user,
            table=table,
            view=view,
            exporter_type=exporter_type,
            state=EXPORT_JOB_PENDING_STATUS,
            export_options=export_options,
        )
        return job

    @staticmethod
    def run_export_job(job) -> ExportJob:
        """
        Given an export job will run the export and store the result in the configured
        storage. Internally it does this in a paginated way to ensure constant memory
        usage, meaning any size export job can be run as long as you have enough time.

        If the export job fails will store the failure on the job itself and mark the
        job as failed.

        :param job: The job to run.
        :return: An updated ExportJob instance with the exported file name.
        """

        # Ensure the user still has permissions when the export job runs.
        table = job.table
        view = job.view
        ExportHandler._raise_if_no_export_permissions(job.user, table, view)
        try:
            return _mark_job_as_finished(_open_file_and_run_export(job))
        except ExportJobCanceledException:
            # If the job was canceled then it must not be marked as failed.
            pass
        except Exception as e:
            _mark_job_as_failed(job, e)
            raise e

    @staticmethod
    def export_file_path(exported_file_name) -> str:
        """
        Given an export file name returns the path to where that export file should be
        put in storage.

        :param exported_file_name: The name of the file to generate a path for.
        :return: The path where this export file should be put in storage.
        """

        return join(settings.EXPORT_FILES_DIRECTORY, exported_file_name)

    @staticmethod
    def is_export_expired(
        job: ExportJob,
        expire_minutes: int = None,
    ) -> bool:
        """
        Whether the file of an export is gone because it aged out, rather than because
        something went wrong. Mirrors what `clean_up_old_jobs` acts on, so the answer
        stays true in the window between a job becoming eligible for cleanup and the
        periodic task getting to it.

        :param job: The export job to check.
        :param expire_minutes: How long an export stays downloadable.
        :return: True when the file is expected to be gone.
        """

        if expire_minutes is None:
            expire_minutes = settings.EXPORT_FILE_EXPIRE_MINUTES

        if job.is_cancelled_or_expired():
            return True

        expired_job_time = datetime.now(tz=timezone.utc) - timedelta(
            minutes=expire_minutes
        )
        return job.created_at <= expired_job_time

    @staticmethod
    def clean_up_old_jobs():
        """
        Cleans up expired export jobs, will delete any files in storage for expired
        jobs with exported files, will cancel any exporting or pending jobs which have
        also expired.
        """

        jobs = ExportJob.jobs_requiring_cleanup(datetime.now(tz=timezone.utc))
        logger.info(f"Cleaning up {jobs.count()} old jobs")
        storage = get_default_storage()
        for job in jobs:
            if job.exported_file_name:
                # Note the django file storage api will not raise an exception if
                # the file does not exist. This is ideal as export jobs first save
                # their exported_file_name and then write to that file, so if the
                # write step fails it is possible that the exported_file_name does not
                # exist.
                storage.delete(ExportHandler.export_file_path(job.exported_file_name))
                job.exported_file_name = None

            job.state = EXPORT_JOB_EXPIRED_STATUS
            job.save()


def _raise_if_invalid_view_or_table_for_exporter(
    exporter_type: str, view: Optional[View]
):
    """
    Raises an exception if the exporter_type does not support the provided view,
    or if no view is provided raises if the exporter does not support exporting just the
    table.

    :param exporter_type: The exporter type to check.
    :param view: None if we are exporting just the table, otherwise the view we are
        exporting.
    """

    exporter = table_exporter_registry.get(exporter_type)
    if not exporter.can_export_table and view is None:
        raise TableOnlyExportUnsupported()
    if view is not None:
        view_type = view_type_registry.get_by_model(view.specific_class)
        if view_type.type not in exporter.supported_views:
            raise ViewUnsupportedForExporterType()


def _raise_if_invalid_order_by_or_filters(
    table: Table, view: Optional[View], export_options: dict
):
    """
    Validates that the filters and order_by specified in export_options only reference
    fields that exist in the table and are visible in the view (if provided).

    This method attempts to apply the filters and ordering to a queryset to catch any
    invalid field references before starting the actual export job. It raises an
    exception if any validation fails.

    :param table: The table where to check the IDs in.
    :param view: Optionally provide a view to check the visible fields off.
    :param export_options: The export options where to extract the filters and order_by
        from.
    """

    model = table.get_model()
    queryset = model.objects.all()

    only_by_field_ids = None
    if view:
        view_type = view_type_registry.get_by_model(view.specific_class)
        visible_field_objects_in_view, model = view_type.get_visible_fields_and_model(
            view
        )
        only_by_field_ids = [f["field"].id for f in visible_field_objects_in_view]

    # Validate the filter object before the job start, so that the validation error
    # can be shown to the user.
    filters_dict = export_options.get("filters", None)
    if filters_dict is not None:
        filters = AdHocFilters.from_dict(filters_dict)
        filters.only_filter_by_field_ids = only_by_field_ids
        filters.apply_to_queryset(model, queryset)

    # Validate the sort object before the job start, so that the validation error
    # can be shown to the user.
    order_by = export_options.get("order_by", None)
    group_by = export_options.get("group_by", None)
    if order_by is not None or group_by is not None:
        queryset.order_by_fields_string(
            order_by or "",
            only_order_by_field_ids=only_by_field_ids,
            group_by_string=group_by,
        )


def _cancel_unfinished_jobs(user):
    """
    Will cancel any in progress jobs by setting their state to cancelled. Any
    tasks currently running these jobs are expected to periodically check if they
    have been cancelled and stop accordingly.

    :param user: The user to cancel all unfinished jobs for.
    :return The number of jobs cancelled.
    """

    if user is None:
        return 0
    else:
        jobs = ExportJob.unfinished_jobs(user=user)
        return jobs.update(state=EXPORT_JOB_CANCELLED_STATUS)


def _mark_job_as_finished(export_job: ExportJob) -> ExportJob:
    """
    Marks the provided job as finished with the result being the provided file name.

    :param export_job: The job to update to be finished.
    :return: The updated finished job.
    """

    export_job.state = EXPORT_JOB_FINISHED_STATUS
    export_job.progress_percentage = 100.0
    export_job.save()
    return export_job


def _mark_job_as_failed(job, e):
    """
    Marks the given export job as failed and stores the exception in the job.

    :param job: The job to mark as failed
    :param e: The exception causing the failure
    :return: The updated failed job.
    """

    job.state = EXPORT_JOB_FAILED_STATUS
    job.progress_percentage = 0.0
    job.error = str(e)
    job.save()
    return job


def _register_action(job):
    """
    Temporary solution to register the action. Refactor this to use the jobs
    system.
    """

    from baserow.core.action.registries import action_type_registry

    from .actions import ExportTableActionType

    action_type_registry.get(ExportTableActionType.type).do(
        job.user, job.table, export_type=job.exporter_type, view=job.view
    )


def _open_file_and_run_export(job: ExportJob) -> ExportJob:
    """
    Using the jobs exporter type exports all data into a new file placed in the
    default storage.

    :return: An updated ExportJob instance with the exported_file_name set.
    """

    exporter: TableExporter = table_exporter_registry.get(job.exporter_type)
    exported_file_name = _generate_random_file_name_with_extension(
        exporter.file_extension
    )
    storage_location = ExportHandler.export_file_path(exported_file_name)
    # Store the file name before we even start exporting so if the export fails
    # and the file has been made we know where it is to clean it up correctly.
    job.exported_file_name = exported_file_name
    job.state = EXPORT_JOB_EXPORTING_STATUS
    job.save()

    # TODO: refactor to use the jobs systems
    _register_action(job)

    filters = job.export_options.pop("filters", None)
    order_by = job.export_options.pop("order_by", None)
    group_by = job.export_options.pop("group_by", None)
    visible_fields_in_order = job.export_options.pop("fields", None)
    include_row_id = job.export_options.pop("include_row_id", True)
    include_primary_field = job.export_options.pop("include_primary_field", True)
    only_by_field_ids = None

    with _create_storage_dir_if_missing_and_open(storage_location) as file:
        queryset_serializer_class = exporter.queryset_serializer_class
        if job.view is None:
            serializer = queryset_serializer_class.for_table(
                job.table,
                include_row_id=include_row_id,
                include_primary_field=include_primary_field,
            )
        else:
            serializer, visible_fields_in_view = queryset_serializer_class.for_view(
                job.view,
                visible_fields_in_order,
                include_row_id=include_row_id,
                include_primary_field=include_primary_field,
            )
            only_by_field_ids = [f["field"].id for f in visible_fields_in_view]

        if filters is not None:
            serializer.add_ad_hoc_filters_dict_to_queryset(
                filters, only_by_field_ids=only_by_field_ids
            )

        if order_by is not None or group_by is not None:
            effective_order_by = order_by or ""
            effective_group_by = group_by or ""

            if job.view is not None:
                if order_by is None:
                    effective_order_by = serialize_sorts_to_string(
                        job.view.viewsort_set.all()
                    )
                if group_by is None:
                    vt = view_type_registry.get_by_model(job.view.specific_class)
                    if vt.can_group_by:
                        effective_group_by = serialize_sorts_to_string(
                            job.view.viewgroupby_set.all()
                        )

            serializer.add_ad_hoc_order_by_to_queryset(
                effective_order_by,
                only_by_field_ids=only_by_field_ids,
                group_by_string=effective_group_by or None,
            )

        serializer.write_to_file(
            PaginatedExportJobFileWriter(file, job), **job.export_options
        )

    _raise_if_export_file_cannot_be_read_back(storage_location)

    return job


def _raise_if_export_file_cannot_be_read_back(storage_location: str):
    """
    Confirms the export really landed in the storage before the job is allowed to
    report success, so a storage problem is reported as a failed export instead of a
    finished one whose download turns out to be broken minutes later.

    This runs in the worker, so it catches a storage that refuses or loses the write
    (no permission, a full disk, an unreachable bucket). It cannot catch a worker and
    a web process that write to different filesystems, because from here the file is
    plainly there -- that split is caught by the shared storage health check and by
    the download endpoints themselves.

    :param storage_location: The path the export was written to.
    :raises ExportJobFileNotWrittenException: When the file cannot be read back.
    """

    # Resolved through the module rather than the name imported above, so this reads
    # back whatever storage the write went to: `_create_storage_dir_if_missing_and_open`
    # picks the default storage from there too.
    storage = core_storage.get_default_storage()

    try:
        written = storage.exists(storage_location)
    except Exception as exc:
        logger.error(
            "Could not read back the export at {} from the storage, where {}.",
            storage_location,
            get_storage_backend_description(),
        )
        raise ExportJobFileNotWrittenException(
            "The exported file could not be read back from the server's file "
            "storage. This usually means the file storage is misconfigured; please "
            "contact an administrator."
        ) from exc

    if not written:
        logger.error(
            "The export at {} is missing from the storage right after being written, "
            "where {}.",
            storage_location,
            get_storage_backend_description(),
        )
        raise ExportJobFileNotWrittenException(
            "The export produced no file in the server's file storage. This usually "
            "means the file storage is misconfigured; please contact an "
            "administrator."
        )


def _generate_random_file_name_with_extension(file_extension):
    return str(uuid.uuid4()) + file_extension
