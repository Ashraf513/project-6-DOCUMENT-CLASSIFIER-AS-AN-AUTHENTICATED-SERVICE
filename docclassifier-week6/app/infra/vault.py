"""
Vault adapter — reads secrets from HashiCorp Vault KV v2.

All application secrets (DB URL, JWT key, MinIO creds, SFTP creds) are
fetched here at startup.  Nothing is hardcoded in source code.

Raises RuntimeError immediately if Vault is unreachable or a secret is
missing, so the container refuses to start rather than running with bad config.
"""

import os

import hvac
import structlog

log = structlog.get_logger()


class VaultClient:
    def __init__(self, addr: str, token: str) -> None:
        self._client = hvac.Client(url=addr, token=token)
        self._verify()

    # ── public ────────────────────────────────────────────────────────────────

    def get_secret(self, path: str, key: str) -> str:
        """Read one key from secret/<path> in KV v2."""
        try:
            response = self._client.secrets.kv.v2.read_secret_version(
                path=path,
                mount_point="secret",
                raise_on_deleted_version=True,
            )
            # KV v2 wraps the payload in an extra "data" layer:
            # response["data"] = version envelope, response["data"]["data"] = actual secrets.
            data: dict = response["data"]["data"]
        except Exception as exc:
            raise RuntimeError(
                f"Vault: failed to read secret at 'secret/{path}': {exc}"
            ) from exc

        if key not in data:
            raise RuntimeError(
                f"Vault: key '{key}' not found in 'secret/{path}'. "
                f"Available keys: {list(data.keys())}"
            )

        value = data[key]
        if not value:
            raise RuntimeError(f"Vault: key '{key}' at 'secret/{path}' is empty.")

        return str(value)

    # ── internal ──────────────────────────────────────────────────────────────

    def _verify(self) -> None:
        # Called in __init__ so the container refuses to start if Vault is
        # unreachable — fail loud at boot beats fail silently on first request.
        try:
            authenticated = self._client.is_authenticated()
        except Exception as exc:
            raise RuntimeError(
                f"Vault unreachable at {self._client.url}: {exc}"
            ) from exc

        if not authenticated:
            raise RuntimeError("Vault authentication failed — check VAULT_TOKEN.")

        log.info("vault_connected", addr=self._client.url)


def load_vault() -> VaultClient:
    """Build a VaultClient from environment variables.

    VAULT_ADDR  — Vault server URL  (default: http://vault:8200)
    VAULT_TOKEN — root / app token  (required, never hardcoded)
    """
    addr = os.environ.get("VAULT_ADDR", "http://vault:8200")
    token = os.environ.get("VAULT_TOKEN", "")
    # Raise before attempting a connection: an empty token is misconfiguration,
    # not a network error — the message should point at the real cause.
    if not token:
        raise RuntimeError(
            "VAULT_TOKEN environment variable is not set. "
            "Cannot start without Vault access."
        )
    return VaultClient(addr, token)
