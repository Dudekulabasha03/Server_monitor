"""
Credential Provider — fetches BMC credentials from Vault, with env fallback.

NEVER store BMC passwords in the database. This provider abstracts the source.
"""
import os
from typing import Optional, Dict
import structlog

from app.config import settings

log = structlog.get_logger(__name__)


class CredentialProvider:
    """
    Resolves BMC credentials for a server.

    Lookup order:
      1. HashiCorp Vault at secret/fleet-monitor/servers/<server_id>
      2. Per-server env override
      3. Global default env (DEFAULT_BMC_USERNAME / DEFAULT_BMC_PASSWORD) — dev/lab only
    """

    def __init__(self):
        self._vault_client = None
        if settings.VAULT_TOKEN:
            try:
                import hvac
                self._vault_client = hvac.Client(url=settings.VAULT_URL, token=settings.VAULT_TOKEN)
            except Exception as e:
                log.warning("vault_init_failed", error=str(e))

    async def get_credentials(self, server_id: str, server=None) -> Optional[Dict[str, str]]:
        # 0. Per-server credentials stored on the Server row (highest priority for mixed-cred fleets)
        if server is not None and getattr(server, "bmc_username", None) and getattr(server, "bmc_password", None):
            return {"username": server.bmc_username, "password": server.bmc_password}

        # 1. Vault
        if self._vault_client:
            try:
                path = f"{settings.VAULT_SECRET_PATH}/servers/{server_id}"
                secret = self._vault_client.secrets.kv.v2.read_secret_version(path=path)
                data = secret["data"]["data"]
                if data.get("username") and data.get("password"):
                    return {"username": data["username"], "password": data["password"]}
            except Exception as e:
                log.debug("vault_lookup_miss", server_id=server_id, error=str(e))

        # 2/3. Env fallback (dev/lab)
        username = os.getenv("DEFAULT_BMC_USERNAME")
        password = os.getenv("DEFAULT_BMC_PASSWORD")
        if username and password:
            return {"username": username, "password": password}

        return None


class OSCredentialProvider:
    """Resolves OS (SSH) credentials for a server. Mirrors CredentialProvider for the OS plane."""

    def __init__(self):
        self._vault_client = None
        if settings.VAULT_TOKEN:
            try:
                import hvac
                self._vault_client = hvac.Client(url=settings.VAULT_URL, token=settings.VAULT_TOKEN)
            except Exception as e:
                log.warning("vault_init_failed", error=str(e))

    async def get_credentials(self, server_id: str, server=None) -> Optional[Dict[str, str]]:
        # 0. Per-server OS credentials on the Server row (highest priority)
        if server is not None and getattr(server, "os_username", None) and getattr(server, "os_password", None):
            return {"username": server.os_username, "password": server.os_password}

        if self._vault_client:
            try:
                path = f"{settings.VAULT_SECRET_PATH}/os/{server_id}"
                secret = self._vault_client.secrets.kv.v2.read_secret_version(path=path)
                data = secret["data"]["data"]
                if data.get("username") and data.get("password"):
                    return {"username": data["username"], "password": data["password"]}
            except Exception as e:
                log.debug("vault_os_lookup_miss", server_id=server_id, error=str(e))

        username = os.getenv("DEFAULT_OS_USERNAME")
        password = os.getenv("DEFAULT_OS_PASSWORD")
        if username and password:
            return {"username": username, "password": password}
        return None
