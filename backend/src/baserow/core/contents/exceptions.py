class ContentsTooLarge(Exception):
    """
    Raised when the requested contents exceed the maximum amount of rows that may be
    returned synchronously.
    """

    def __init__(self, row_count: int, maximum: int):
        self.row_count = row_count
        self.maximum = maximum
        super().__init__(
            f"The requested contents contain {row_count} rows, which is more than the "
            f"maximum of {maximum} that can be returned in one request."
        )
