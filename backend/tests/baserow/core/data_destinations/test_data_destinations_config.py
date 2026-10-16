import json

from django.core.exceptions import ImproperlyConfigured

import pytest

from baserow.core.data_destinations.config import (
    ALL_PURPOSES,
    PURPOSE_BACKUP,
    DataDestinationConfig,
    parse_data_destinations_env,
)

S3_DESTINATION = {
    "name": "lake",
    "type": "s3",
    "bucket": "baserow-lake",
    "prefix": "/exports/",
    "endpoint_url": "http://minio:9000",
    "access_key_id": "key",
    "secret_access_key": "secret",
}


def _env(*destinations):
    return json.dumps(list(destinations))


def test_empty_env_returns_no_destinations():
    assert parse_data_destinations_env(None) == []
    assert parse_data_destinations_env("") == []
    assert parse_data_destinations_env("   ") == []


def test_valid_s3_destination_is_parsed_with_defaults():
    [destination] = parse_data_destinations_env(_env(S3_DESTINATION))

    assert isinstance(destination, DataDestinationConfig)
    assert destination.name == "lake"
    assert destination.type == "s3"
    assert destination.prefix == "exports"
    assert destination.purposes == ALL_PURPOSES
    assert destination.allow_trust_public_key is False
    assert destination.options == {
        "bucket": "baserow-lake",
        "endpoint_url": "http://minio:9000",
    }
    assert destination.secrets == {
        "access_key_id": "key",
        "secret_access_key": "secret",
    }


def test_secrets_are_not_in_the_repr():
    [destination] = parse_data_destinations_env(_env(S3_DESTINATION))

    assert "secret" not in repr(destination).replace("secrets", "")


def test_secret_is_read_from_a_file(tmp_path):
    secret_file = tmp_path / "secret"
    secret_file.write_text("from-file\n")
    entry = dict(S3_DESTINATION)
    del entry["secret_access_key"]
    entry["secret_access_key_file"] = str(secret_file)

    [destination] = parse_data_destinations_env(_env(entry))

    assert destination.secrets["secret_access_key"] == "from-file"


def test_secret_inline_and_file_together_is_rejected(tmp_path):
    entry = dict(S3_DESTINATION, secret_access_key_file=str(tmp_path / "secret"))

    with pytest.raises(ImproperlyConfigured, match="not both"):
        parse_data_destinations_env(_env(entry))


def test_missing_secret_file_is_rejected(tmp_path):
    entry = dict(S3_DESTINATION)
    del entry["secret_access_key"]
    entry["secret_access_key_file"] = str(tmp_path / "missing")

    with pytest.raises(ImproperlyConfigured, match="could not be read"):
        parse_data_destinations_env(_env(entry))


def test_s3_without_static_keys_uses_the_credential_chain():
    entry = {"name": "lake", "type": "s3", "bucket": "baserow-lake"}

    [destination] = parse_data_destinations_env(_env(entry))

    assert destination.secrets == {}


def test_s3_with_half_a_key_pair_is_rejected():
    entry = dict(S3_DESTINATION)
    del entry["secret_access_key"]

    with pytest.raises(ImproperlyConfigured, match="set together"):
        parse_data_destinations_env(_env(entry))


def test_azure_requires_a_credential():
    entry = {"name": "blob", "type": "azure", "container": "c", "account_name": "a"}

    with pytest.raises(ImproperlyConfigured, match="is required"):
        parse_data_destinations_env(_env(entry))


def test_azure_requires_an_account_name_without_connection_string():
    entry = {"name": "blob", "type": "azure", "container": "c", "account_key": "k"}

    with pytest.raises(ImproperlyConfigured, match="account_name"):
        parse_data_destinations_env(_env(entry))


def test_azure_with_a_connection_string_is_valid():
    entry = {
        "name": "blob",
        "type": "azure",
        "container": "c",
        "connection_string": "DefaultEndpointsProtocol=https;AccountName=a",
    }

    [destination] = parse_data_destinations_env(_env(entry))

    assert destination.options == {"container": "c"}


def test_filesystem_root_must_be_absolute():
    entry = {"name": "pvc", "type": "filesystem", "root": "relative/path"}

    with pytest.raises(ImproperlyConfigured, match="absolute"):
        parse_data_destinations_env(_env(entry))


@pytest.mark.parametrize(
    "entry,message",
    [
        ({"type": "s3", "bucket": "b"}, "'name' is required"),
        (dict(S3_DESTINATION, name="not a slug"), "may only contain"),
        (dict(S3_DESTINATION, type="ftp"), "'type' must be one of"),
        (dict(S3_DESTINATION, bukcet="typo"), "unknown keys"),
        (dict(S3_DESTINATION, prefix="exports/../../etc"), "'..'"),
        (dict(S3_DESTINATION, purposes=["archive"]), "unknown purposes"),
        (dict(S3_DESTINATION, purposes=[]), "non-empty list"),
        (dict(S3_DESTINATION, use_ssl="yes"), "must be a boolean"),
        ({"name": "lake", "type": "s3"}, "'bucket' is required"),
    ],
)
def test_malformed_destination_is_rejected(entry, message):
    with pytest.raises(ImproperlyConfigured, match=message):
        parse_data_destinations_env(_env(entry))


def test_purposes_are_restricted():
    [destination] = parse_data_destinations_env(
        _env(dict(S3_DESTINATION, purposes=["backup"]))
    )

    assert destination.purposes == (PURPOSE_BACKUP,)
    assert destination.allows("backup")
    assert not destination.allows("datalake")


def test_duplicate_names_are_rejected():
    with pytest.raises(ImproperlyConfigured, match="duplicate"):
        parse_data_destinations_env(_env(S3_DESTINATION, S3_DESTINATION))


def test_invalid_json_fails_fast():
    with pytest.raises(ImproperlyConfigured, match="not valid JSON"):
        parse_data_destinations_env("{not json")


def test_non_list_json_fails_fast():
    with pytest.raises(ImproperlyConfigured, match="JSON list"):
        parse_data_destinations_env(json.dumps(S3_DESTINATION))


def test_s3_server_side_encryption_options_are_parsed():
    [destination] = parse_data_destinations_env(
        _env(
            {
                **S3_DESTINATION,
                "server_side_encryption": "aws:kms",
                "sse_kms_key_id": "alias/backups",
            }
        )
    )
    assert destination.options["server_side_encryption"] == "aws:kms"
    assert destination.options["sse_kms_key_id"] == "alias/backups"

    [destination] = parse_data_destinations_env(
        _env({**S3_DESTINATION, "server_side_encryption": "AES256"})
    )
    assert destination.options["server_side_encryption"] == "AES256"


def test_s3_server_side_encryption_is_validated():
    with pytest.raises(ImproperlyConfigured, match="server_side_encryption"):
        parse_data_destinations_env(
            _env({**S3_DESTINATION, "server_side_encryption": "rot13"})
        )

    with pytest.raises(ImproperlyConfigured, match="sse_kms_key_id"):
        parse_data_destinations_env(_env({**S3_DESTINATION, "sse_kms_key_id": "k"}))

    with pytest.raises(ImproperlyConfigured, match="sse_kms_key_id"):
        parse_data_destinations_env(
            _env(
                {
                    **S3_DESTINATION,
                    "server_side_encryption": "AES256",
                    "sse_kms_key_id": "k",
                }
            )
        )
