"""
HashiCorp Vault KV-v2 client.

All application secrets are resolved through this module at startup.
If Vault is unreachable or the secret is missing the call raises RuntimeError,
which prevents api/worker from booting (per the brief).

Environment variables required:
    VAULT_ADDR  — e.g. http://vault:8200
    VAULT_TOKEN — root token in dev mode (from .env)

The KV mount is "secret" and all app secrets live at path "docclassifier".
"""

import os
import hvac


_client: hvac.Client | None = None
_MOUNT  = "secret"
_PATH   = "docclassifier"


def _get_client() -> hvac.Client:
    global _client
    if _client is not None:
        return _client

    addr  = os.environ.get("VAULT_ADDR",  "http://vault:8200")
    token = os.environ.get("VAULT_TOKEN", "")

    client = hvac.Client(url=addr, token=token)
    if not client.is_authenticated():
        raise RuntimeError(
            f"Vault authentication failed — check VAULT_ADDR ({addr}) and VAULT_TOKEN"
        )

    _client = client
    return _client


def get_secret(key: str) -> str:
    """
    Fetch *key* from Vault KV-v2 at secret/docclassifier.

    Raises RuntimeError if Vault is unreachable or the key is absent.
    """
    client = _get_client()
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
