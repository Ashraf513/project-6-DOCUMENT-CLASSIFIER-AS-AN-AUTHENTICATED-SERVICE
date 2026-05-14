# Location: app/infra/vault.py
# Stub for local development – reads secrets from environment variables.
# In production, replace this with actual HashiCorp Vault logic.

import os

def get_secret(key: str) -> str:
    """Return the secret stored under *key* (from environment)."""
    return os.getenv(key)