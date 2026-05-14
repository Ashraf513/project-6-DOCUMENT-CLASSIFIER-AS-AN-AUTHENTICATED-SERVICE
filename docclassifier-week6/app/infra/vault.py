import os

import hvac


VAULT_ADDR = os.getenv("VAULT_ADDR", "http://vault:8200")
VAULT_TOKEN = os.getenv("VAULT_TOKEN", "root")


client = hvac.Client(
    url=VAULT_ADDR,
    token=VAULT_TOKEN,
)


def get_secret(key: str) -> str:
    """
    Read a secret from Vault KV v2.
    """

    if not client.is_authenticated():
        raise RuntimeError("Vault authentication failed")

    response = client.secrets.kv.v2.read_secret_version(
        path="docclassifier"
    )

    data = response["data"]["data"]

    if key not in data:
        raise RuntimeError(f"Secret '{key}' not found in Vault")

    return data[key]