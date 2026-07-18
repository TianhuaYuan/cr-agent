"""JWT 工具（HS256）。

复用 1 号项目 ai-resume-analyzer 的 JWT 思路（access token + 验证依赖），
但 cr-agent 是单操作者代码审查工具，省去 refresh token，只发 access token。
密钥来自 settings.JWT_SECRET（HS256 对称签名）。

设计要点（面试可讲）：
- 签发/验证集中在这一处，API 与 MCP 共用，避免两套实现漂移。
- 默认 API_AUTH_REQUIRED=False（开发态免鉴权，便利）；生产部署设 True + 自定义 JWT_SECRET。
- is_valid_token 把"解码异常"归一为布尔，方便依赖/中间件直接判权。
"""
import logging
import time

import jwt

from backend.core.config import settings

logger = logging.getLogger(__name__)

_ALGO = "HS256"


def create_access_token(subject: str, expires_minutes: int | None = None) -> str:
    """签发 HS256 access token。

    Args:
        subject: token 主题（这里固定 "operator"，单操作者）。
        expires_minutes: 过期分钟数；缺省用 settings.JWT_EXPIRE_MINUTES。
    """
    exp = expires_minutes if expires_minutes is not None else settings.JWT_EXPIRE_MINUTES
    now = int(time.time())
    payload = {"sub": subject, "iat": now, "exp": now + exp * 60}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=_ALGO)


def decode_token(token: str) -> dict:
    """验证并解码 JWT。无效/过期/签名错 → 抛 jwt.PyJWTError 子类。"""
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[_ALGO])


def is_valid_token(token: str | None) -> bool:
    """token 是否有效（非空且签名/过期均通过）。"""
    if not token:
        return False
    try:
        decode_token(token)
        return True
    except jwt.PyJWTError:
        return False
