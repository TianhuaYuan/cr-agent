"""Task 18.3: 健康检查端点。

GET /api/v1/health — 供 Railway healthcheck 调用，验证服务存活。
不需要鉴权（Railway 无法提供 JWT）。
"""
from fastapi import APIRouter

from backend.core.database import engine

router = APIRouter()


@router.get("/health")
async def health_check():
    """健康检查：验证 DB 连通性 + 服务状态。

    返回:
        status: "ok" | "degraded"
        version: 应用版本
        db: "ok" | "fail"（数据库连通性）
    """
    result = {
        "status": "ok",
        "version": "0.1.0",
        "db": "ok",
    }

    # 验证数据库连通性
    try:
        from sqlalchemy import text
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        result["db"] = "fail"
        result["status"] = "degraded"

    return result
