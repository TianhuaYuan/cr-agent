"""MCP Gateway JWT 鉴权集成测试（TDD RED → GREEN）。

验证 API_AUTH_REQUIRED=True 时，/mcp 需 Bearer；默认 False 时现有 test_mcp.py 不受影响。
MCP 鉴权用轻量 ASGI BearerAuthMiddleware 包 _mcp_app，不在中间件缓冲响应体（流式安全）。
"""
import json
from contextlib import asynccontextmanager

import httpx
import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport

_MCP_HEADERS = {"Accept": "application/json, text/event-stream"}


def _jsonrpc(method: str, params: dict, id_: int = 0) -> dict:
    return {"jsonrpc": "2.0", "method": method, "params": params, "id": id_}


@asynccontextmanager
async def _mcp_auth_client(monkeypatch):
    """开启鉴权的 MCP HTTP 测试客户端。"""
    from backend.core.config import settings
    from backend.core import llm as llm_mod
    from backend.main import create_app, _mcp_app

    # 复用 W1 E2E 假客户端（避免真实 LLM 调用）
    class _Fake:
        @property
        def chat(self):
            async def _create(*a, **kw):
                from types import SimpleNamespace
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content="[]"))]
                )
            return SimpleNamespace(completions=SimpleNamespace(create=_create))

    monkeypatch.setattr(llm_mod, "get_chat_client", lambda: _Fake())
    monkeypatch.setattr(settings, "API_AUTH_REQUIRED", True)
    monkeypatch.setattr(settings, "JWT_SECRET", "test-secret-0000000000000000000000")

    async with LifespanManager(_mcp_app):
        app = create_app()
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test", follow_redirects=True
        ) as client:
            yield client


@pytest.mark.asyncio
async def test_mcp_requires_auth_without_token(monkeypatch):
    """无 Authorization → 401（中间件拦截，未到达 MCP）。"""
    async with _mcp_auth_client(monkeypatch) as client:
        resp = await client.post(
            "/mcp/",
            json=_jsonrpc("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "t", "version": "1"},
            }),
            headers=_MCP_HEADERS,
        )
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_mcp_allows_with_valid_token(monkeypatch):
    """有效 Bearer → 非 401（中间件放行，请求到达 MCP）。"""
    from backend.core import security

    async with _mcp_auth_client(monkeypatch) as client:
        tok = security.create_access_token("operator", expires_minutes=30)
        resp = await client.post(
            "/mcp/",
            json=_jsonrpc("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "t", "version": "1"},
            }),
            headers={**_MCP_HEADERS, "Authorization": f"Bearer {tok}"},
        )
        assert resp.status_code != 401
