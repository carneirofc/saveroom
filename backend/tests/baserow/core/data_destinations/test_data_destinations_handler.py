import json
from io import BytesIO

import boto3
import pytest
from moto import mock_aws

from baserow.core.data_destinations.config import parse_data_destinations_env
from baserow.core.data_destinations.exceptions import (
    DataDestinationDoesNotExist,
    DataDestinationPurposeNotAllowed,
    InvalidDataDestinationKey,
)
from baserow.core.data_destinations.handler import DataDestinationHandler


def _configure(settings, *destinations):
    settings.BASEROW_DATA_DESTINATIONS = parse_data_destinations_env(
        json.dumps(list(destinations))
    )


@pytest.fixture
def filesystem_destination(settings, tmp_path):
    _configure(
        settings,
        {
            "name": "pvc",
            "type": "filesystem",
            "root": str(tmp_path),
            "prefix": "baserow",
            "purposes": ["backup"],
        },
    )
    return DataDestinationHandler().get_destination("pvc")


def test_get_destination(filesystem_destination):
    handler = DataDestinationHandler()

    assert handler.get_destination("pvc", purpose="backup") == filesystem_destination
    assert handler.list_destinations(purpose="datalake") == []

    with pytest.raises(DataDestinationDoesNotExist):
        handler.get_destination("missing")

    with pytest.raises(DataDestinationPurposeNotAllowed):
        handler.get_destination("pvc", purpose="datalake")


def test_filesystem_round_trip_is_rooted_at_the_prefix(
    filesystem_destination, tmp_path
):
    handler = DataDestinationHandler()
    storage = handler.get_storage(filesystem_destination)

    handler.save_file(storage, "a/b/data.bin", BytesIO(b"first"))
    # Writing the same key again replaces the object instead of renaming it.
    handler.save_file(storage, "a/b/data.bin", BytesIO(b"second"))
    handler.write_json(storage, "a/manifest.json", {"rows": 3})

    assert (tmp_path / "baserow" / "a" / "b" / "data.bin").read_bytes() == b"second"
    assert handler.read_json(storage, "a/manifest.json") == {"rows": 3}
    assert handler.list_keys(storage) == ["a/b/data.bin", "a/manifest.json"]
    assert handler.list_keys(storage, "a/b") == ["a/b/data.bin"]
    assert handler.list_keys(storage, "does/not/exist") == []

    handler.delete_keys(storage, ["a/b/data.bin"])

    assert handler.list_keys(storage) == ["a/manifest.json"]


@pytest.mark.parametrize("key", ["", "/", "../escape", "a/../../b", "a\\b", "./a"])
def test_keys_that_could_escape_the_prefix_are_rejected(key):
    with pytest.raises(InvalidDataDestinationKey):
        DataDestinationHandler().normalize_key(key)


def test_keys_are_normalized():
    assert DataDestinationHandler().normalize_key("/a//b/c.json") == "a/b/c.json"


@mock_aws
def test_s3_round_trip(settings):
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="lake")
    _configure(
        settings,
        {
            "name": "lake",
            "type": "s3",
            "bucket": "lake",
            "prefix": "exports",
            "region": "us-east-1",
            "access_key_id": "testing",
            "secret_access_key": "testing",
        },
    )
    handler = DataDestinationHandler()
    storage = handler.get_storage(handler.get_destination("lake"))

    handler.save_file(storage, "table=1/part-0.parquet", BytesIO(b"parquet"))
    handler.write_json(storage, "table=1/_manifest.json", {"ok": True})

    objects = boto3.client("s3", region_name="us-east-1").list_objects_v2(Bucket="lake")
    assert sorted(item["Key"] for item in objects["Contents"]) == [
        "exports/table=1/_manifest.json",
        "exports/table=1/part-0.parquet",
    ]
    assert handler.list_keys(storage, "table=1") == [
        "table=1/_manifest.json",
        "table=1/part-0.parquet",
    ]
    assert handler.read_json(storage, "table=1/_manifest.json") == {"ok": True}


def test_azure_storage_is_built_from_the_config(settings, mocker):
    azure_storage = mocker.patch("storages.backends.azure_storage.AzureStorage")
    _configure(
        settings,
        {
            "name": "blob",
            "type": "azure",
            "container": "backups",
            "account_name": "account",
            "account_key": "key",
            "prefix": "baserow",
        },
    )
    handler = DataDestinationHandler()

    handler.get_storage(handler.get_destination("blob"))

    azure_storage.assert_called_once_with(
        azure_container="backups",
        location="baserow",
        overwrite_files=True,
        account_name="account",
        account_key="key",
    )


def _storage(*destinations):
    from baserow.core.data_destinations.registries import (
        data_destination_type_registry,
    )

    [config] = parse_data_destinations_env(json.dumps(list(destinations)))
    return data_destination_type_registry.get(config.type).build_storage(config)


def test_s3_storage_is_built_from_the_destination():
    storage = _storage(
        {
            "name": "minio",
            "type": "s3",
            "bucket": "lake",
            "prefix": "exports",
            "region": "eu-west-1",
            "endpoint_url": "http://minio:9000",
            "addressing_style": "path",
            "access_key_id": "key",
            "secret_access_key": "secret",
            "server_side_encryption": "aws:kms",
            "sse_kms_key_id": "alias/backups",
        }
    )

    assert storage.bucket_name == "lake"
    assert storage.location == "exports"
    assert storage.region_name == "eu-west-1"
    assert storage.endpoint_url == "http://minio:9000"
    assert storage.addressing_style == "path"
    assert storage.access_key == "key"
    assert storage.secret_key == "secret"
    assert storage.object_parameters == {
        "ServerSideEncryption": "aws:kms",
        "SSEKMSKeyId": "alias/backups",
    }


def test_s3_storage_without_static_keys_or_encryption():
    storage = _storage({"name": "plain", "type": "s3", "bucket": "lake"})

    assert not storage.access_key
    assert not storage.secret_key
    assert "ServerSideEncryption" not in storage.object_parameters


def test_azure_storage_credentials():
    storage = _storage(
        {
            "name": "az",
            "type": "azure",
            "container": "backups",
            "account_name": "acct",
            "account_key": "k",
        }
    )
    assert storage.azure_container == "backups"
    assert storage.account_name == "acct"
    assert storage.account_key == "k"

    storage = _storage(
        {
            "name": "az",
            "type": "azure",
            "container": "backups",
            "connection_string": "UseDevelopmentStorage=true",
        }
    )
    assert storage.connection_string == "UseDevelopmentStorage=true"

    storage = _storage(
        {
            "name": "az",
            "type": "azure",
            "container": "backups",
            "account_name": "acct",
            "sas_token": "sv=1",
        }
    )
    assert storage.sas_token == "sv=1"
