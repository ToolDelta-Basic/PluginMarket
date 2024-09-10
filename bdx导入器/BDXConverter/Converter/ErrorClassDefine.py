class HeaderError(Exception):
    """
    Header error occurred while reading header in BDX file
    """

    def __init__(self, header: bytes):
        Exception.__init__(self, f'find invalid file header {header}')


class ReadError(Exception):
    """
    BDX file read error
    """

    def __init__(self, errorOccurredPosition: int):
        Exception.__init__(
            self, f'failed to convert this BDX file, and the error occurred at position {errorOccurredPosition}')


class UnknownOperationError(Exception):
    """
    Find unknown operation error
    """

    def __init__(self, operationId: int, errorOccurredPosition: int):
        Exception.__init__(
            self, f'an unknown operation {operationId} was found, and the error occurred at position {errorOccurredPosition}')


class SignatureError(Exception):
    """
    Error occurred while signing
    """

    def __init__(self, errorContent: str):
        Exception.__init__(self, errorContent)
