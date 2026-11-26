class ApplicationError(RuntimeError):
    """Base error translated into an API problem response."""


class ConflictError(ApplicationError):
    pass


class NotFoundError(ApplicationError):
    pass
