# Location: app/services/exceptions.py
# Purpose: Domain‑level exceptions raised by services.
# Routers translate these to appropriate HTTP status codes.

class ServiceError(Exception):
    """Base for all service layer exceptions."""
    pass

class PermissionDenied(ServiceError):
    """Actor lacks required permissions."""
    pass

class NotFound(ServiceError):
    """Requested entity does not exist."""
    pass

class LastAdminError(ServiceError):
    """Cannot demote the last remaining admin."""
    pass

class RelabelNotAllowed(ServiceError):
    """Reviewer may only relabel predictions with confidence < 0.7."""
    pass

class InvalidStateTransition(ServiceError):
    """Batch status transition rule violated."""
    pass