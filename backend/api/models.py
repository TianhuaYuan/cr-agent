"""Task 17.1: GET /api/v1/models 端点。

返回当前配置的 6 个角色的 model 名称，供前端模型选择面板使用。
"""
from fastapi import APIRouter

from backend.core.config import settings

router = APIRouter()


@router.get("/models")
async def get_models():
    """返回当前配置的 6 个角色的 model 名称。

    无需鉴权，只暴露 model 名称（无敏感信息）。
    """
    return {
        "decompose": settings.DECOMPOSE_MODEL,
        "worker.quality": settings.WORKER_QUALITY_MODEL,
        "worker.security": settings.WORKER_SECURITY_MODEL,
        "worker.performance": settings.WORKER_PERFORMANCE_MODEL,
        "worker.structure": settings.WORKER_STRUCTURE_MODEL,
        "judge": settings.JUDGE_MODEL,
    }
