"""FastAPI 应用工厂（Task 6.1 + Task 8.4 MCP 挂载）。

create_app() 模式：测试和运行时共用同一套路由装配逻辑。
lifespan 阶段校验配置 + 建表（dev 用 SQLite，生产用 alembic 迁移后可移除建表）。
Task 8.4: MCP Server 挂载到 /mcp 路径，支持 Streamable HTTP 传输。

关键坑（面试可讲）：
- **Mounted app lifespan 不自动触发**：Starlette 的 app.mount() 只转发 HTTP 请求，
  不转发 ASGI lifespan 事件。MCP StreamableHTTPASGIApp 需要 lifespan 初始化
  session_manager / task_group，否则 RuntimeError: Task group is not initialized。
  解法：在 FastAPI lifespan 中手动触发 _mcp_app.router.lifespan_context()。
  测试中用 asgi-lifespan 的 LifespanManager 单独触发（ASGITransport 不触发 lifespan）。
- **path 映射**：http_app(path="/") 让 MCP 内部路由在 /，FastAPI mount 剥离 /mcp 前缀后
  请求正确映射到 MCP app 的根路由。默认 path="/mcp" 会导致 /mcp/mcp/ 双重前缀 404。
"""
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backend.api.auth import router as auth_router
from backend.api.evaluation import router as evaluation_router
from backend.api.health import router as health_router
from backend.api.models import router as models_router
from backend.api.reviews import router as reviews_router
from backend.api.webhooks import router as webhooks_router
from backend.core.config import settings, validate_required_settings
from backend.core.database import init_db
from backend.core.security import is_valid_token
from backend.mcp.server import mcp

logger = logging.getLogger(__name__)


# ── MCP Starlette app（模块级单例）──────────────────────────
# stateless_http=True → 每个请求独立处理，无需 session 管理
# path="/" → MCP 内部路由在 /，配合 FastAPI mount("/mcp", ...) 正确映射
_mcp_app = mcp.http_app(transport="streamable-http", stateless_http=True, path="/")


class _BearerAuthMiddleware:
    """MCP Gateway 的 Bearer 鉴权中间件（轻量 ASGI 包装）。

    为什么不用 FastAPI dependency：MCP 走 FastMCP 的 streamable-http 传输，
    不是普通 FastAPI 路由，无法直接挂 Depends。这里在 ASGI 层拦截：
    请求开始时校验 Authorization: Bearer，无效即返回 401，合法则原样委托给
    内层 _mcp_app（**不缓冲响应体**，流式/SSE 透传，不影响 MCP 传输）。

    verify 闭包实时读 settings.API_AUTH_REQUIRED：开发态(False)直接放行，
    生产态(True)必须有效 token——与 API 侧 require_auth 同策略。
    """

    def __init__(self, app, verify):
        self.app = app
        self.verify = verify

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http":
            token = self._extract_token(scope)
            if not self.verify(token):
                await self._send_401(send)
                return
        await self.app(scope, receive, send)

    @staticmethod
    def _extract_token(scope) -> str | None:
        headers = dict(scope.get("headers", []))
        auth = headers.get(b"authorization")
        if not auth:
            return None
        parts = auth.decode("latin-1").split(" ", 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1].strip()
        return None

    @staticmethod
    async def _send_401(send):
        body = json.dumps({"detail": "missing or invalid token"}).encode()
        await send({
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
        })
        await send({"type": "http.response.body", "body": body})


def _verify_mcp_token(token: str | None) -> bool:
    """MCP 鉴权判定：开发态放行；生产态要求有效 JWT。"""
    if not settings.API_AUTH_REQUIRED:
        return True
    return is_valid_token(token)


# 用鉴权中间件包一层（模块级单例，避免 create_app 重复包装）
_mcp_auth_app = _BearerAuthMiddleware(_mcp_app, _verify_mcp_token)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动：校验配置 + 建表 + MCP lifespan；关闭：清理资源。

    关键：mounted sub-app 的 lifespan 不会自动触发，需手动调用。
    """
    validate_required_settings()
    # 安全护栏：生产态开启鉴权却仍用默认占位密钥 → 醒目告警（防误部署）
    if settings.API_AUTH_REQUIRED and settings.JWT_SECRET.startswith("dev-insecure-secret"):
        logger.warning(
            "⚠️ API_AUTH_REQUIRED=True 但 JWT_SECRET 仍是默认值，请通过 "
            "CR_AGENT_JWT_SECRET 配置自定义密钥，否则 token 可被轻易伪造！"
        )
    await init_db()
    # 手动触发 MCP sub-app 的 lifespan（初始化 session_manager / task_group）
    async with _mcp_app.router.lifespan_context(_mcp_app):
        logger.info("cr-agent 服务启动完成（含 MCP Gateway /mcp）")
        yield
    logger.info("cr-agent 服务关闭")


def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用实例。"""
    app = FastAPI(
        title="cr-agent",
        description="多 Agent 代码审查协作平台",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(reviews_router, prefix="/api/v1")
    app.include_router(models_router, prefix="/api/v1")
    app.include_router(health_router, prefix="/api/v1")
    # 评测 API（C 功能后端，Task 3）
    app.include_router(evaluation_router, prefix="/api/v1")
    # JWT 签发端点（Task：API/MCP 鉴权）
    app.include_router(auth_router, prefix="/api/v1")
    # GitHub Webhook 端点（Task 9.3）
    app.include_router(webhooks_router, prefix="/api/v1")
    # MCP Gateway:挂载带 Bearer 鉴权的 FastMCP Starlette app 到 /mcp 路径
    app.mount("/mcp", _mcp_auth_app)

    # 静态前端:托管 backend/static/ 下的测试用单文件页面(Playground)。
    # 必须放在所有 API router include 之后——mount("/") 会兜底所有未匹配路径,
    # 若先挂会抢占 /api/v1/... 和 /mcp/...。这里用 html=True 让 / 自动返回 index.html。
    static_dir = Path(__file__).resolve().parent / "static"
    if static_dir.is_dir():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
    return app


# 模块级实例（uvicorn backend.main:app 直接引用）
app = create_app()
