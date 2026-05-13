"""
Password hashing for the service layer.

Uses bcrypt directly (no passlib).  bcrypt is what fastapi-users uses
internally, so hashes produced here are compatible with fastapi-users'
verifier when Hussien wires auth.

The service layer calls hash_password() before handing the value to the
user repository, and calls verify_password() during login.  Routers and
repos do not import this module.

bcrypt has a hard 72-byte input limit.  We pre-hash with SHA-256 so
longer passwords are accepted without truncation surprises - this is
the same workaround Django and fastapi-users use.
"""

from __future__ import annotations

import base64
import hashlib

import bcrypt


def _prepare(plain: str) -> bytes:
    """SHA-256 pre-hash to sidestep bcrypt's 72-byte input limit."""
    digest = hashlib.sha256(plain.encode("utf-8")).digest()
    return base64.b64encode(digest)


def hash_password(plain: str) -> str:
    """Return a bcrypt hash string for a plain-text password."""
    return bcrypt.hashpw(_prepare(plain), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plain-text password against a stored bcrypt hash."""
    try:
        return bcrypt.checkpw(_prepare(plain), hashed.encode("utf-8"))
    except ValueError:
        # Malformed hash on disk - treat as a verification failure.
        return False
