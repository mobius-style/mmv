class MobiusRuntimeError(Exception):
    """Base runtime error."""


class VllmConnectionError(MobiusRuntimeError):
    pass


class RetrievalUnavailableError(MobiusRuntimeError):
    pass


class WebSearchUnavailableError(MobiusRuntimeError):
    pass
