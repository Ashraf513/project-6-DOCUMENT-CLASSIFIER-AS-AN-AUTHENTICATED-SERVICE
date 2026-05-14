"""
Password hashing for the service layer.

Uses pwdlib, the same library fastapi-users 15+ uses internally.
By sharing pwdlib's recommended hasher (Argon2id), hashes written by
the service round-trip cleanly through fastapi-users' login verifier
and vice-versa.

The service layer calls hash_password() before handing the value to the
user repository, and verify_password() is available for any non-fastapi-users
verification (admin scripts, integration tests).  Routers and repos do
not import this module.
"""

from __future__ import annotations

from pwdlib import PasswordHash


# Shared instance.  PasswordHash.recommended() picks Argon2id and is the
# default fastapi-users uses, so hashes are interchangeable.
_pwd = PasswordHash.recommended()


def hash_password(plain: str) -> str:
    """Return an Argon2id hash string for a plain-text password."""
    return _pwd.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plain-text password against a stored Argon2id hash."""
    try:
        return _pwd.verify(plain, hashed)
    except Exception:
        # Malformed or unknown-scheme hash on disk - treat as failure.
        return False