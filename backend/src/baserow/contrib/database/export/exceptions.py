class ExportJobCanceledException(Exception):
    pass


class TableOnlyExportUnsupported(Exception):
    pass


class ViewUnsupportedForExporterType(Exception):
    pass


class ExportJobDoesNotExistException(Exception):
    pass


class ExportJobFileNotWrittenException(Exception):
    """
    Raised when an export finished writing but its file cannot be read back from the
    storage. The job is failed rather than finished, so the user is told the export
    did not work instead of being handed a download that cannot be served.
    """
