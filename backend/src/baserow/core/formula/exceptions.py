from django.conf import settings

from celery.exceptions import SoftTimeLimitExceeded
from loguru import logger

from baserow.core.formula.parser.exceptions import BaserowFormulaException


class RuntimeFormulaException(BaserowFormulaException):
    """Raised when manipulating an invalid formula"""


class RuntimeFormulaRecursion(RuntimeFormulaException):
    """Raised when the formula context detects a recursion."""

    def __init__(self, *args, **kwargs):
        super().__init__("Formula recursion detected", *args, **kwargs)


class InvalidRuntimeFormula(RuntimeFormulaException):
    """Raised when manipulating an invalid formula"""


class InvalidFormulaContext(RuntimeFormulaException):
    """
    The provided formula context is not valid.
    """


class InvalidFormulaContextContent(RuntimeFormulaException):
    """
    The content of formula context is not valid.
    """


def formula_exception_handler(e):
    """
    Logs formula errors in non debug mode. In debug mode raises the exception.

    :param e: The exception to report.
    """

    if isinstance(e, SoftTimeLimitExceeded):
        # The task is out of time. Swallowing this would let it write empty values
        # and run on until the hard time limit kills it.
        raise e
    if settings.DEBUG or settings.TESTS:
        # We want to see any issues immediately in debug mode.
        raise e
    logger.error(
        f"Formula related error occurred: {e}. Please send this error to the baserow "
        f"developers at https://github.com/carneirofc/baserow/issues."
    )
    logger.exception(e)
