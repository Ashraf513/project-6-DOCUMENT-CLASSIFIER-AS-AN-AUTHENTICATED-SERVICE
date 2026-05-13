# Location: app/domain/errors.py
# Purpose: Domain-level exceptions raised by the service layer.
# Routers catch these and translate them into HTTP status codes.
# Services never raise HTTPException directly.


class DomainError(Exception):
    """Base class for all service-layer errors."""


class NotFound(DomainError):
    """Raised when an entity cannot be located by its identifier."""


class PermissionDenied(DomainError):
    """Raised when the actor lacks the role required for an action."""


class LastAdminError(DomainError):
    """Raised when an operation would leave the system with zero admins."""


class InvalidStateTransition(DomainError):
    """Raised when a batch/prediction is asked to move to an illegal state."""


class RelabelNotAllowed(DomainError):
    """Raised when a reviewer attempts to relabel a high-confidence prediction."""
