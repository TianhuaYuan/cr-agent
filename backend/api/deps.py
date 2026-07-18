"""API 层依赖注入。

- get_db：数据库会话（从 backend.core.database re-export）。
- require_auth：JWT Bearer 鉴权依赖，挂在受保护路由上（如 /reviews）。
"""
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.core.config import settings
from backend.core.database import get_db
from backend.core.security import is_valid_token

__all__ = ["get_db", "require_auth"]

_bearer = HTTPBearer(auto_error=False)


async def require_auth(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
) -> str:
    """JWT Bearer 鉴权依赖。

    - API_AUTH_REQUIRED=False（默认，开发态）：放行，返回 "anonymous"。
    - API_AUTH_REQUIRED=True：必须带有效 Bearer token，否则 401。

    与 WEBHOOK_SECRET_REQUIRED 同款的 fail-open 开发态策略：默认不挡，
    生产靠配置开关收紧。判权逻辑用 is_valid_token 归一化（解码异常 → False）。
    """
    if not settings.API_AUTH_REQUIRED:
        return creds.subject if creds else "anonymous"
    if creds is None or not is_valid_token(creds.credentials):
        raise HTTPException(status_code=401, detail="missing or invalid token")
    return creds.credentials
