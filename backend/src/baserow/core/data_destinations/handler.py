import json
from typing import IO, Any, Dict, List, Optional

from django.conf import settings
from django.core.files import File
from django.core.files.base import ContentFile
from django.core.files.storage import Storage

from .config import DataDestinationConfig
from .exceptions import (
    DataDestinationDoesNotExist,
    DataDestinationPurposeNotAllowed,
    InvalidDataDestinationKey,
)
from .registries import data_destination_type_registry


class DataDestinationHandler:
    """
    Resolves env-declared destinations and performs the few storage operations that
    backups and table exports need. Every key is relative to the destination prefix.
    """

    def list_destinations(
        self, purpose: Optional[str] = None
    ) -> List[DataDestinationConfig]:
        """
        Lists the configured destinations.

        :param purpose: When given, only the destinations declared for it.
        :return: The matching destination configs.
        """

        destinations = list(getattr(settings, "BASEROW_DATA_DESTINATIONS", []))
        if purpose is None:
            return destinations
        return [
            destination for destination in destinations if destination.allows(purpose)
        ]

    def get_destination(
        self, name: str, purpose: Optional[str] = None
    ) -> DataDestinationConfig:
        """
        Fetches a configured destination by name.

        :param name: The name of the destination.
        :param purpose: When given, the destination must be declared for it.
        :raises DataDestinationDoesNotExist: When no destination has that name.
        :raises DataDestinationPurposeNotAllowed: When the destination is not
            declared for the purpose.
        :return: The destination config.
        """

        for destination in self.list_destinations():
            if destination.name == name:
                if purpose is not None and not destination.allows(purpose):
                    raise DataDestinationPurposeNotAllowed(
                        f"The data destination '{name}' may not be used for "
                        f"'{purpose}'."
                    )
                return destination

        raise DataDestinationDoesNotExist(
            f"The data destination '{name}' is not configured."
        )

    def get_storage(self, destination: DataDestinationConfig) -> Storage:
        """
        Builds the storage of a destination, rooted at its prefix.

        :param destination: The destination config.
        :return: A Django storage instance.
        """

        return data_destination_type_registry.get(destination.type).build_storage(
            destination
        )

    def normalize_key(self, key: str) -> str:
        """
        Validates an object key and strips its surrounding slashes.

        :param key: The key relative to the destination prefix.
        :raises InvalidDataDestinationKey: When the key is empty or could escape the
            destination prefix.
        :return: The normalized key.
        """

        if not isinstance(key, str) or "\\" in key or "\x00" in key:
            raise InvalidDataDestinationKey(f"The key '{key}' is not valid.")

        segments = [segment for segment in key.split("/") if segment]
        if not segments or any(segment in (".", "..") for segment in segments):
            raise InvalidDataDestinationKey(f"The key '{key}' is not valid.")

        return "/".join(segments)

    def save_file(self, storage: Storage, key: str, content: IO[bytes]) -> str:
        """
        Writes a file at exactly the given key, replacing an existing object.

        :param storage: The destination storage.
        :param key: The key to write to.
        :param content: A readable binary file object.
        :return: The key the file was written to.
        """

        key = self.normalize_key(key)

        # The filesystem storage renames instead of overwriting, which would break
        # the deterministic layout, so an existing object is removed first.
        if storage.exists(key):
            storage.delete(key)

        saved = storage.save(
            key, content if isinstance(content, File) else File(content)
        )

        if saved != key:
            raise InvalidDataDestinationKey(
                f"The storage wrote '{saved}' instead of the requested key '{key}'."
            )
        return saved

    def write_json(self, storage: Storage, key: str, data: Any) -> str:
        """
        Writes a JSON document at the given key.

        :param storage: The destination storage.
        :param key: The key to write to.
        :param data: A JSON serializable object.
        :return: The key the document was written to.
        """

        payload = json.dumps(data, indent=2, sort_keys=True, default=str)
        return self.save_file(storage, key, ContentFile(payload.encode("utf-8")))

    def read_json(self, storage: Storage, key: str) -> Dict[str, Any]:
        """
        Reads a JSON document.

        :param storage: The destination storage.
        :param key: The key to read.
        :return: The decoded document.
        """

        with storage.open(self.normalize_key(key), "rb") as handle:
            return json.loads(handle.read().decode("utf-8"))

    def list_keys(self, storage: Storage, prefix: str = "") -> List[str]:
        """
        Lists every object key under a prefix, recursively.

        :param storage: The destination storage.
        :param prefix: The prefix to list, empty for everything.
        :return: The sorted keys, relative to the destination prefix.
        """

        root = self.normalize_key(prefix) if prefix.strip("/") else ""
        keys: List[str] = []
        pending = [root]

        while pending:
            directory = pending.pop()
            try:
                directories, files = storage.listdir(directory)
            except FileNotFoundError:
                continue

            for name in files:
                keys.append(f"{directory}/{name}" if directory else name)
            for name in directories:
                pending.append(f"{directory}/{name}" if directory else name)

        return sorted(keys)

    def delete_keys(self, storage: Storage, keys: List[str]) -> int:
        """
        Deletes the given objects, ignoring the ones that are already gone.

        :param storage: The destination storage.
        :param keys: The keys to delete.
        :return: The number of keys that were requested for deletion.
        """

        for key in keys:
            storage.delete(self.normalize_key(key))
        return len(keys)
