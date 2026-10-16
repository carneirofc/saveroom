"""
Parsing and validation of the env-declared data destinations.

A data destination is an external object store (S3 or S3-compatible, Azure Blob
Storage, or a mounted filesystem) that backups and datalake table exports are written
to. Destinations are declared entirely through the ``BASEROW_DATA_DESTINATIONS``
environment variable as a JSON list, so credentials never live in the database: models
and API payloads only ever reference a destination by its name.

Secrets can be given inline or, preferably, through a ``<key>_file`` path whose content
is read once at startup, which works with Docker and Kubernetes secret mounts.

IMPORTANT: this module is imported from ``config/settings/base.py`` while Django
settings are still being evaluated (before the app registry is ready). Keep it
import-light — stdlib and ``django.core.exceptions`` only — and never import Django
models or storage backends here, or settings evaluation will break.
"""

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Tuple

from django.core.exceptions import ImproperlyConfigured

ENV_NAME = "BASEROW_DATA_DESTINATIONS"

TYPE_S3 = "s3"
TYPE_AZURE = "azure"
TYPE_FILESYSTEM = "filesystem"

PURPOSE_BACKUP = "backup"
PURPOSE_DATALAKE = "datalake"
ALL_PURPOSES = (PURPOSE_BACKUP, PURPOSE_DATALAKE)

# The keys every destination accepts, whatever its type.
COMMON_KEYS = {"name", "type", "prefix", "purposes", "allow_trust_public_key"}

# Per type: required option keys, optional string keys, optional boolean keys, and the
# secret keys that may also be given as `<key>_file`.
TYPE_SPECS: Dict[str, Dict[str, Tuple[str, ...]]] = {
    TYPE_S3: {
        "required": ("bucket",),
        "strings": (
            "region",
            "endpoint_url",
            "addressing_style",
            "signature_version",
            "server_side_encryption",
            "sse_kms_key_id",
        ),
        "booleans": ("use_ssl", "verify"),
        "secrets": ("access_key_id", "secret_access_key", "session_token"),
    },
    TYPE_AZURE: {
        "required": ("container",),
        "strings": ("account_name", "endpoint_suffix", "custom_domain"),
        "booleans": (),
        "secrets": ("account_key", "connection_string", "sas_token"),
    },
    TYPE_FILESYSTEM: {
        "required": ("root",),
        "strings": (),
        "booleans": (),
        "secrets": (),
    },
}

# The S3 server-side encryption modes a destination may request on every upload.
S3_SERVER_SIDE_ENCRYPTION_MODES = ("AES256", "aws:kms")

# A destination name is referenced from models and URLs, so keep it a url-safe slug.
_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


@dataclass(frozen=True)
class DataDestinationConfig:
    """A single env-declared data destination."""

    name: str
    type: str
    # The key prefix every object of this destination is written under, without
    # leading or trailing slashes. Empty means the root of the bucket or directory.
    prefix: str = ""
    # What the destination may be used for, a subset of `ALL_PURPOSES`.
    purposes: Tuple[str, ...] = ALL_PURPOSES
    # Whether a staff member may trust the signing key of a backup restored from this
    # destination when the archive was made by another instance.
    allow_trust_public_key: bool = False
    # The non-secret, type specific options.
    options: Mapping[str, Any] = field(default_factory=dict)
    # The resolved secrets. Excluded from the repr so they never end up in logs.
    secrets: Mapping[str, str] = field(default_factory=dict, repr=False)

    def allows(self, purpose: str) -> bool:
        return purpose in self.purposes


def _prefix(index: int) -> str:
    return f"{ENV_NAME}[{index}]"


def _require_str(entry: Dict[str, Any], key: str, index: int) -> str:
    value = entry.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ImproperlyConfigured(
            f"{_prefix(index)}: '{key}' is required and must be a non-empty string."
        )
    return value.strip()


def _optional_str(entry: Dict[str, Any], key: str, index: int) -> Optional[str]:
    value = entry.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ImproperlyConfigured(
            f"{_prefix(index)}: '{key}' must be a non-empty string when provided."
        )
    return value.strip()


def _optional_bool(entry: Dict[str, Any], key: str, index: int) -> Optional[bool]:
    value = entry.get(key)
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ImproperlyConfigured(f"{_prefix(index)}: '{key}' must be a boolean.")
    return value


def normalize_prefix(value: str, where: str) -> str:
    """
    Strips the slashes around a key prefix and refuses one that could escape the
    destination root.

    :param value: The raw prefix.
    :param where: Where the prefix comes from, used in the error message.
    :raises ImproperlyConfigured: When the prefix contains `..` or backslashes.
    :return: The normalized prefix, possibly empty.
    """

    if "\\" in value:
        raise ImproperlyConfigured(f"{where}: 'prefix' must not contain backslashes.")

    segments = [segment for segment in value.strip().split("/") if segment]
    if any(segment in (".", "..") for segment in segments):
        raise ImproperlyConfigured(
            f"{where}: 'prefix' must not contain '.' or '..' segments."
        )
    return "/".join(segments)


def _secret(entry: Dict[str, Any], key: str, index: int) -> Optional[str]:
    """
    Resolves a secret given either inline as `key` or as a path in `key_file`.
    """

    file_key = f"{key}_file"
    has_inline = key in entry
    has_file = file_key in entry

    if has_inline and has_file:
        raise ImproperlyConfigured(
            f"{_prefix(index)}: set either '{key}' or '{file_key}', not both."
        )

    if has_inline:
        return _require_str(entry, key, index)

    if has_file:
        path = _require_str(entry, file_key, index)
        try:
            with open(path, "r", encoding="utf-8") as handle:
                value = handle.read().strip()
        except OSError as exc:
            raise ImproperlyConfigured(
                f"{_prefix(index)}: '{file_key}' could not be read: {exc.strerror}."
            ) from exc
        if not value:
            raise ImproperlyConfigured(
                f"{_prefix(index)}: the file in '{file_key}' is empty."
            )
        return value

    return None


def _purposes(entry: Dict[str, Any], index: int) -> Tuple[str, ...]:
    value = entry.get("purposes", list(ALL_PURPOSES))
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(item, str) for item in value)
    ):
        raise ImproperlyConfigured(
            f"{_prefix(index)}: 'purposes' must be a non-empty list of strings."
        )
    unknown = sorted(set(value) - set(ALL_PURPOSES))
    if unknown:
        raise ImproperlyConfigured(
            f"{_prefix(index)}: unknown purposes {unknown}, allowed are "
            f"{list(ALL_PURPOSES)}."
        )
    return tuple(purpose for purpose in ALL_PURPOSES if purpose in value)


def _validate_destination(entry: Any, index: int) -> DataDestinationConfig:
    if not isinstance(entry, dict):
        raise ImproperlyConfigured(
            f"{_prefix(index)}: each destination must be a JSON object."
        )

    name = _require_str(entry, "name", index)
    if not _NAME_RE.match(name):
        raise ImproperlyConfigured(
            f"{_prefix(index)}: 'name' ('{name}') may only contain letters, digits, "
            f"hyphens and underscores."
        )

    destination_type = _require_str(entry, "type", index)
    spec = TYPE_SPECS.get(destination_type)
    if spec is None:
        raise ImproperlyConfigured(
            f"{_prefix(index)}: 'type' must be one of {sorted(TYPE_SPECS)}."
        )

    # Refuse unknown keys: a typo in a credential or option key would otherwise be
    # silently ignored and only surface when the first export fails.
    allowed_keys = (
        COMMON_KEYS
        | set(spec["required"])
        | set(spec["strings"])
        | set(spec["booleans"])
        | set(spec["secrets"])
        | {f"{key}_file" for key in spec["secrets"]}
    )
    unknown_keys = sorted(set(entry) - allowed_keys)
    if unknown_keys:
        raise ImproperlyConfigured(
            f"{_prefix(index)}: unknown keys {unknown_keys} for a "
            f"'{destination_type}' destination."
        )

    prefix = entry.get("prefix", "")
    if not isinstance(prefix, str):
        raise ImproperlyConfigured(f"{_prefix(index)}: 'prefix' must be a string.")
    prefix = normalize_prefix(prefix, _prefix(index))

    allow_trust_public_key = _optional_bool(entry, "allow_trust_public_key", index)

    options: Dict[str, Any] = {}
    for key in spec["required"]:
        options[key] = _require_str(entry, key, index)
    for key in spec["strings"]:
        value = _optional_str(entry, key, index)
        if value is not None:
            options[key] = value
    for key in spec["booleans"]:
        value = _optional_bool(entry, key, index)
        if value is not None:
            options[key] = value

    secrets: Dict[str, str] = {}
    for key in spec["secrets"]:
        value = _secret(entry, key, index)
        if value is not None:
            secrets[key] = value

    if destination_type == TYPE_S3:
        # Without static keys boto3 falls back to its credential chain (instance
        # profile, IRSA, env), but a lone half of a key pair is always a mistake.
        if ("access_key_id" in secrets) != ("secret_access_key" in secrets):
            raise ImproperlyConfigured(
                f"{_prefix(index)}: 'access_key_id' and 'secret_access_key' must be "
                f"set together."
            )
        encryption = options.get("server_side_encryption")
        if encryption is not None and encryption not in S3_SERVER_SIDE_ENCRYPTION_MODES:
            raise ImproperlyConfigured(
                f"{_prefix(index)}: 'server_side_encryption' must be one of "
                f"{list(S3_SERVER_SIDE_ENCRYPTION_MODES)}."
            )
        if "sse_kms_key_id" in options and encryption != "aws:kms":
            raise ImproperlyConfigured(
                f"{_prefix(index)}: 'sse_kms_key_id' requires 'server_side_encryption' "
                f"to be 'aws:kms'."
            )
    elif destination_type == TYPE_AZURE:
        if not secrets:
            raise ImproperlyConfigured(
                f"{_prefix(index)}: one of 'account_key', 'connection_string' or "
                f"'sas_token' is required."
            )
        if "connection_string" not in secrets and "account_name" not in options:
            raise ImproperlyConfigured(
                f"{_prefix(index)}: 'account_name' is required unless "
                f"'connection_string' is set."
            )
    elif destination_type == TYPE_FILESYSTEM:
        if not os.path.isabs(options["root"]):
            raise ImproperlyConfigured(
                f"{_prefix(index)}: 'root' must be an absolute path."
            )

    return DataDestinationConfig(
        name=name,
        type=destination_type,
        prefix=prefix,
        purposes=_purposes(entry, index),
        allow_trust_public_key=bool(allow_trust_public_key),
        options=options,
        secrets=secrets,
    )


def parse_data_destinations_env(raw: Optional[str]) -> List[DataDestinationConfig]:
    """
    Parses and validates the ``BASEROW_DATA_DESTINATIONS`` environment value.

    :param raw: The raw JSON string (or None / empty when unset).
    :raises ImproperlyConfigured: When the JSON is invalid or a destination is
        malformed.
    :return: The list of validated destination configs (possibly empty).
    """

    if raw is None or not raw.strip():
        return []

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ImproperlyConfigured(f"{ENV_NAME} is not valid JSON: {exc}.") from exc

    if not isinstance(data, list):
        raise ImproperlyConfigured(
            f"{ENV_NAME} must be a JSON list of destination objects."
        )

    destinations: List[DataDestinationConfig] = []
    seen_names = set()
    for index, entry in enumerate(data):
        config = _validate_destination(entry, index)
        if config.name in seen_names:
            raise ImproperlyConfigured(
                f"{ENV_NAME}: duplicate destination name '{config.name}'."
            )
        seen_names.add(config.name)
        destinations.append(config)

    return destinations
