class DataDestinationDoesNotExist(Exception):
    """Raised when no destination with the requested name is configured."""


class DataDestinationPurposeNotAllowed(Exception):
    """Raised when a destination is used for a purpose it is not declared for."""


class InvalidDataDestinationKey(Exception):
    """Raised when an object key could escape the destination prefix."""
