from unittest.mock import MagicMock

from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage

import pytest

from baserow.core.storage import (
    FileNotFoundInStorage,
    StorageUnavailable,
    check_file_in_storage,
    get_storage_backend_description,
    stream_file_from_storage,
)


@pytest.fixture
def storage_with_file(tmpdir):
    storage = FileSystemStorage(location=str(tmpdir), base_url="http://localhost")
    storage.save("export_files/archive.zip", ContentFile(b"hello world"))
    return storage


def test_check_file_in_storage_returns_the_size(storage_with_file):
    assert check_file_in_storage("export_files/archive.zip", storage_with_file) == 11


def test_check_file_in_storage_raises_when_the_file_is_gone(storage_with_file):
    with pytest.raises(FileNotFoundInStorage) as exc:
        check_file_in_storage("export_files/gone.zip", storage_with_file)

    assert exc.value.path == "export_files/gone.zip"


def test_check_file_in_storage_raises_when_the_storage_is_unreachable():
    storage = MagicMock()
    storage.exists.side_effect = ConnectionError("the endpoint is unreachable")

    with pytest.raises(StorageUnavailable) as exc:
        check_file_in_storage("export_files/archive.zip", storage)

    # The caller needs the cause for the logs, but the message must not carry the
    # endpoint or the credentials into an API response.
    assert isinstance(exc.value.original_exception, ConnectionError)


@pytest.mark.django_db
def test_stream_file_from_storage_streams_the_content(storage_with_file):
    response = stream_file_from_storage(
        "export_files/archive.zip", "my export.zip", storage_with_file
    )

    try:
        assert b"".join(response.streaming_content) == b"hello world"
        assert response["Content-Length"] == "11"
        assert response["Content-Type"] == "application/octet-stream"
        assert "attachment" in response["Content-Disposition"]
        assert "my export.zip" in response["Content-Disposition"]
        assert response["X-Content-Type-Options"] == "nosniff"
        assert response["Cache-Control"] == "private, no-store"
    finally:
        response.close()


@pytest.mark.django_db
def test_stream_file_from_storage_closes_the_handle(storage_with_file):
    response = stream_file_from_storage(
        "export_files/archive.zip", "archive.zip", storage_with_file
    )
    file_handle = response.file_to_stream

    response.close()

    assert file_handle.closed


def test_stream_file_from_storage_sets_a_length_without_fileno(storage_with_file):
    """
    The S3 file object supports neither `getbuffer()` nor `fileno()`, so FileResponse
    cannot work the length out by itself and would fall back to chunked encoding.
    """

    real_file = storage_with_file.open("export_files/archive.zip", "rb")
    s3_like_handle = MagicMock(wraps=real_file)
    del s3_like_handle.getbuffer
    del s3_like_handle.fileno

    storage = MagicMock()
    storage.exists.return_value = True
    storage.size.return_value = 11
    storage.open.return_value = s3_like_handle

    response = stream_file_from_storage(
        "export_files/archive.zip", "archive.zip", storage
    )

    try:
        assert response["Content-Length"] == "11"
    finally:
        real_file.close()


def test_stream_file_from_storage_raises_when_the_file_is_gone(storage_with_file):
    with pytest.raises(FileNotFoundInStorage):
        stream_file_from_storage("export_files/gone.zip", "gone.zip", storage_with_file)


@pytest.mark.django_db
def test_storage_backend_description_names_media_root(settings):
    settings.STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}
    }
    settings.MEDIA_ROOT = "/baserow/media"

    description = get_storage_backend_description()

    # An operator reading this in a failed download needs to be pointed at the actual
    # misconfiguration, not merely told a file is missing.
    assert "/baserow/media" in description
    assert "ReadWriteMany" in description


@pytest.mark.django_db
def test_storage_backend_description_names_the_bucket(settings):
    settings.STORAGES = {
        "default": {"BACKEND": "storages.backends.s3boto3.S3Boto3Storage"}
    }
    settings.AWS_STORAGE_BUCKET_NAME = "baserow-media"

    assert "baserow-media" in get_storage_backend_description()
