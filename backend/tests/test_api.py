"""Phase 6 API 测试（Task 6.1）。

用 httpx AsyncClient + ASGITransport 测 FastAPI 路由，
in-memory SQLite + mock LLM，全链路免真实依赖。
"""
import json
from types import SimpleNamespace

import httpx
import pytest_asyncio
from httpx import ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.core.database import Base, get_db


class _SmartClient:
    """API 测试用假 LLM：decompose 返回任务列表，worker 返回 findings。"""

    _TASKS = json.dumps([
        {"role": "security", "description": "检查安全漏洞", "priority": 1},
        {"role": "quality", "description": "检查代码风格", "priority": 2},
    ])
    _FINDINGS = json.dumps([
        {
            "severity": "high",
            "line": 1,
            "description": "硬编码密钥",
            "suggestion": "用环境变量",
            "code_snippet": "api_key='sk-xxx'",
        },
    ])

    @property
    def chat(self):
        async def _create(*a, **kw):
            messages = kw.get("messages", [])
            user_content = next(
                (m.get("content", "") for m in messages if m.get("role") == "user"), ""
            )
            text = self._TASKS if "拆解" in user_content or "priority" in user_content else self._FINDINGS
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=text))]
            )

        return SimpleNamespace(completions=SimpleNamespace(create=_create))


@pytest_asyncio.fixture
async def api_client(monkeypatch):
    """完整 API 测试客户端：内存 DB + mock LLM + httpx。"""
    # 先 import models 确保 Base.metadata 注册了所有表（独立运行时不依赖其他测试模块）
    import backend.models  # noqa: F401

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _override_get_db():
        async with maker() as session:
            yield session

    monkeypatch.setattr("backend.core.llm.get_chat_client", lambda: _SmartClient())

    from backend.main import create_app

    app = create_app()
    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    await engine.dispose()


class TestReviewAPI:
    """POST /api/v1/reviews + GET /api/v1/reviews/{id}。"""

    async def test_create_review(self, api_client):
        """POST → 200 + review_id + status=completed。"""
        resp = await api_client.post("/api/v1/reviews", json={
            "code": "api_key = 'sk-xxx'\nx = 1",
            "language": "python",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "review_id" in data
        assert data["status"] == "completed"

    async def test_get_review(self, api_client):
        """GET → 200 + report 非空。"""
        resp = await api_client.post("/api/v1/reviews", json={
            "code": "x = 1",
            "language": "python",
        })
        review_id = resp.json()["review_id"]

        resp2 = await api_client.get(f"/api/v1/reviews/{review_id}")
        assert resp2.status_code == 200
        data = resp2.json()
        assert data["status"] == "completed"
        assert data["report"] is not None
        assert len(data["report"]) > 0

    async def test_get_nonexistent(self, api_client):
        """GET 不存在的 ID → 404。"""
        resp = await api_client.get("/api/v1/reviews/99999")
        assert resp.status_code == 404

    async def test_validation_empty_code(self, api_client):
        """POST 空代码 → 422。"""
        resp = await api_client.post("/api/v1/reviews", json={
            "code": "",
            "language": "python",
        })
        assert resp.status_code == 422

    async def test_validation_bad_language(self, api_client):
        """POST 不支持的语言 → 422。"""
        resp = await api_client.post("/api/v1/reviews", json={
            "code": "x = 1",
            "language": "ruby",
        })
        assert resp.status_code == 422
