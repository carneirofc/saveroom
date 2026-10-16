class ApiClientDoesNotExist(Exception):
    """Raised when the requested API client does not exist."""


class ApiClientKeyDoesNotExist(Exception):
    """Raised when the requested API client key does not exist."""


class ApiClientDoesNotBelongToUser(Exception):
    """Raised when an API client does not belong to the given user."""


class InvalidApiClientScope(Exception):
    """Raised when a scope that is not part of the known scopes is provided."""


class MaximumUniqueApiClientKeyTriesError(Exception):
    """
    Raised when the maximum amount of tries has been exceeded while generating a
    unique API client key prefix.
    """
