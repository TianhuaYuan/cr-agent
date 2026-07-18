"""鉴权路由：签发 JWT（/auth/token）。

单操作者工具，无需注册/登录流程：持有 API_KEY 的一方调用 /auth/token 换取
有时效的 Bearer token，之后带该 token 访问受保护路由（/reviews）与 MCP Gateway。

- API_AUTH_REQUIRED=False（开发态）：任何人可换 token（便利）。
- API_AUTH_REQUIRED=True：必须提供正确的 API_KEY，否则 401（防匿名换 token）。
"""
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.core.config import settings
from backend.core.security import create_access_token

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


class TokenRequest(BaseModel):
    api_key: str = ""


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/token", response_model=TokenResponse)
async def issue_token(req: TokenRequest):
    """用 API_KEY 换取 JWT access token。"""
    if settings.API_AUTH_REQUIRED and req.api_key != settings.API_KEY:
        raise HTTPException(status_code=401, detail="invalid api_key")
    token = create_access_token("operator", expires_minutes=settings.JWT_EXPIRE_MINUTES)
    return TokenResponse(access_token=token)
