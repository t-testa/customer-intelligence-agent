class NotFoundError(Exception):
    """Requested domain entity does not exist."""


class ConflictError(Exception):
    """Persisted state does not allow this operation."""


class PolicyError(Exception):
    """An untrusted operation failed authorization or validation."""


class ModelError(Exception):
    """Model integration failed safely."""
