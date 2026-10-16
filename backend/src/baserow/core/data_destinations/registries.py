import os

from django.core.files.storage import FileSystemStorage, Storage

from baserow.core.registry import Instance, Registry

from .config import TYPE_AZURE, TYPE_FILESYSTEM, TYPE_S3, DataDestinationConfig


class DataDestinationType(Instance):
    """
    Turns an env-declared destination config into a Django storage. The storage is
    rooted at the destination prefix, so callers only ever deal with relative keys.
    """

    def build_storage(self, config: DataDestinationConfig) -> Storage:
        raise NotImplementedError


class S3DataDestinationType(DataDestinationType):
    type = TYPE_S3

    def build_storage(self, config: DataDestinationConfig) -> Storage:
        # Imported lazily so instances that never use S3 do not pay for boto3.
        from storages.backends.s3 import S3Storage

        options = config.options
        kwargs = {
            "bucket_name": options["bucket"],
            "location": config.prefix,
            # Objects are private and keys are chosen by us, so an existing key is
            # replaced rather than renamed.
            "default_acl": None,
            "file_overwrite": True,
            "querystring_auth": False,
        }
        optional = {
            "region_name": options.get("region"),
            "endpoint_url": options.get("endpoint_url"),
            "addressing_style": options.get("addressing_style"),
            "signature_version": options.get("signature_version"),
            "use_ssl": options.get("use_ssl"),
            "verify": options.get("verify"),
            "access_key": config.secrets.get("access_key_id"),
            "secret_key": config.secrets.get("secret_access_key"),
            "security_token": config.secrets.get("session_token"),
        }
        kwargs.update(
            {key: value for key, value in optional.items() if value is not None}
        )
        # Server-side encryption is requested on every upload of this destination.
        object_parameters = {
            parameter: options[option]
            for option, parameter in (
                ("server_side_encryption", "ServerSideEncryption"),
                ("sse_kms_key_id", "SSEKMSKeyId"),
            )
            if option in options
        }
        if object_parameters:
            kwargs["object_parameters"] = object_parameters
        return S3Storage(**kwargs)


class AzureDataDestinationType(DataDestinationType):
    type = TYPE_AZURE

    def build_storage(self, config: DataDestinationConfig) -> Storage:
        from storages.backends.azure_storage import AzureStorage

        options = config.options
        kwargs = {
            "azure_container": options["container"],
            "location": config.prefix,
            "overwrite_files": True,
        }
        optional = {
            "account_name": options.get("account_name"),
            "endpoint_suffix": options.get("endpoint_suffix"),
            "custom_domain": options.get("custom_domain"),
            "account_key": config.secrets.get("account_key"),
            "connection_string": config.secrets.get("connection_string"),
            "sas_token": config.secrets.get("sas_token"),
        }
        kwargs.update(
            {key: value for key, value in optional.items() if value is not None}
        )
        return AzureStorage(**kwargs)


class FileSystemDataDestinationType(DataDestinationType):
    type = TYPE_FILESYSTEM

    def build_storage(self, config: DataDestinationConfig) -> Storage:
        location = os.path.join(config.options["root"], config.prefix)
        return FileSystemStorage(location=location, base_url=None)


class DataDestinationTypeRegistry(Registry[DataDestinationType]):
    name = "data_destination_type"


data_destination_type_registry = DataDestinationTypeRegistry()
data_destination_type_registry.register(S3DataDestinationType())
data_destination_type_registry.register(AzureDataDestinationType())
data_destination_type_registry.register(FileSystemDataDestinationType())
