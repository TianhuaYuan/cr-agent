"""Worker 注册表 —— role → Worker 实例 的单一来源。

Supervisor 图（services/supervisor/graph.py）与 MCP Server（mcp/server.py）
都复用这份映射，避免两处各维护一份完全相同的 ``_WORKERS``
（去重，见 W3 代码审查 P2 项）。

Worker 无状态，模块级单例复用即可。
"""
from backend.services.workers.base import BaseWorker
from backend.services.workers.performance import PerformanceWorker
from backend.services.workers.quality import QualityWorker
from backend.services.workers.security import SecurityWorker
from backend.services.workers.structure import StructureWorker

# role → 无状态 Worker 实例（模块级单例）
WORKERS: dict[str, BaseWorker] = {
    "quality": QualityWorker(),
    "security": SecurityWorker(),
    "performance": PerformanceWorker(),
    "structure": StructureWorker(),
}

# 系统支持的 Worker 角色（有序，供路由白名单/校验使用）
SUPPORTED_ROLES: tuple[str, ...] = tuple(WORKERS.keys())
