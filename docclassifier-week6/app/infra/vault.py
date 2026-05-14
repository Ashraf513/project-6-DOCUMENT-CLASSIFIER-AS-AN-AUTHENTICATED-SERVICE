"""
HashiCorp Vault KV-v2 client — with local‑dev fallback.

In production (Docker Compose), VAULT_ADDR and VAULT_TOKEN are set
and secrets are fetched from the Vault server.

For local development without Vault, leave VAULT_ADDR unset and secrets
will be read from environment variables (e.g. JWT_SECRET).
"""

import os
import hvac


_client: hvac.Client | None = None
_MOUNT  = "secret"
_PATH   = "docclassifier"


def _get_client() -> hvac.Client | None:
    """Return a Vault client if Vault is configured, otherwise None."""
    global _client
    if _client is not None:
        return _client

    addr  = os.environ.get("VAULT_ADDR", "")
    token = os.environ.get("VAULT_TOKEN", "")

    if not addr or not token:
        # No Vault configuration — fall back to environment variables
        _client = False   # flag value
        return None

    client = hvac.Client(url=addr, token=token)
    if not client.is_authenticated():
        raise RuntimeError(
            f"Vault authentication failed — check VAULT_ADDR ({addr}) and VAULT_TOKEN"
        )
    _client = client
    return _client


def get_secret(key: str) -> str:
    """
    Return the secret for *key*.

    If Vault is configured, reads from KV-v2 at secret/docclassifier.
    Otherwise falls back to the environment variable named *key*.
    """
    client = _get_client()
    if client is None or client is False:
        # Local‑dev fallback
        value = os.environ.get(key, "")
        if not value:
            raise RuntimeError(
                f"Secret '{key}' not set in environment (and Vault is not configured)"
            )
        return value

    # Vault path
    try:
        response = client.secrets.kv.v2.read_secret_version(
            path=_PATH,
            mount_point=_MOUNT,
            raise_on_deleted_version=True,
        )
    except Exception as exc:
        raise RuntimeError(f"Could not read secrets from Vault: {exc}") from exc

    data = response.get("data", {}).get("data", {})
    value = data.get(key)
    if value is None:
        raise RuntimeError(f"Secret '{key}' not found at Vault path {_MOUNT}/{_PATH}")
    return value