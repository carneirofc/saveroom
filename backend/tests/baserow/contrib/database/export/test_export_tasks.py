from unittest.mock import MagicMock, patch

import pytest
from celery.exceptions import Ignore

from baserow.contrib.database.export.handler import ExportHandler
from baserow.contrib.database.export.models import EXPORT_JOB_FAILED_STATUS
from baserow.contrib.database.export.tasks import run_export_job
from baserow.core.storage import get_default_storage


@pytest.mark.django_db
def test_run_export_job_skips_nonexisting_jobs():
    non_existing_job_id = 999
    with pytest.raises(Ignore):
        run_export_job(non_existing_job_id)


@pytest.mark.django_db
def test_an_export_whose_file_is_not_written_fails_instead_of_finishing(
    data_fixture, use_tmp_media_root
):
    """
    A finished job with no file behind it is the worst outcome: the user is shown a
    download button that fails later, with nothing saying why. Failing the job puts
    the storage problem where the user is already looking.
    """

    user = data_fixture.create_user()
    table = data_fixture.create_database_table(user=user)
    data_fixture.create_text_field(table=table, name="text_field")

    job = ExportHandler.create_pending_export_job(
        user, table, None, {"exporter_type": "csv"}
    )

    storage = MagicMock(wraps=get_default_storage())
    # The write succeeds and the read back does not: a storage that silently drops
    # writes, or a volume that is not really there.
    storage.exists.return_value = False

    with patch("baserow.core.storage.get_default_storage", return_value=storage):
        with pytest.raises(Exception):
            ExportHandler.run_export_job(job)

    job.refresh_from_db()
    assert job.state == EXPORT_JOB_FAILED_STATUS
    assert "file storage" in job.error
