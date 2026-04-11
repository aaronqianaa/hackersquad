from dataclasses import dataclass

from fastapi import Header, HTTPException

from app.core.config import settings


@dataclass
class AuthContext:
    tenant_id: str | None


def get_auth_context(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
) -> AuthContext:
    if settings.api_key and x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    if settings.require_tenant_header and not x_tenant_id:
        raise HTTPException(status_code=401, detail="Missing tenant header")
    return AuthContext(tenant_id=x_tenant_id)
