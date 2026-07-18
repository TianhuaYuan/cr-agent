"""API JWT 鉴权集成测试（TDD RED → GREEN）。

默认 API_AUTH_REQUIRED=False → 现有 test_api.py 的 /reviews 测试不受影响。
本文件验证 API_AUTH_REQUIRED=True 时：/reviews 需 Bearer、/auth/token 签发。
"""
import json
from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.core.database import Base, get_db


class _SmartClient:
    """API 鉴权测试用假 LLM（只返回固定 findings，够触发 graph 跑通）。"""

    _FINDINGS = json.dumps([
        {
            "severity": "high",
            "line": 1,
            "description": "硬编码密钥",
            "suggestion": "用环境变量",
            "code_snippet": "api_key='sk-xxx'",
        }
    ])

    @property
    def chat(self):
        async def _create(*a, **kw):
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=self._FINDINGS))]
            )

        return SimpleNamespace(completions=SimpleNamespace(create=_create))


@pytest_asyncio.fixture
async def auth_client(monkeypatch):
    """开启鉴权的 API 测试客户端：内存 DB + mock LLM + API_AUTH_REQUIRED=True。"""
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
    # 开启鉴权 + 固定密钥/凭证，确保测试可复现
    monkeypatch.setattr("backend.core.config.settings.API_AUTH_REQUIRED", True)
    monkeypatch.setattr("backend.core.config.settings.API_KEY", "test-key")
    monkeypatch.setattr("backend.core.config.settings.JWT_SECRET", "test-secret-0000000000000000000000")

    from backend.main import create_app

    app = create_app()
    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    await engine.dispose()


async def _issue_token(client, api_key="test-key"):
    return await client.post("/api/v1/auth/token", json={"api_key": api_key})


async def test_auth_token_endpoint_issues_token(auth_client):
    """/auth/token 返回 200 + access_token。"""
    resp = await _issue_token(auth_client)
    assert resp.status_code == 200
    assert "access_token" in resp.json()


async def test_reviews_requires_auth_without_token(auth_client):
    """无 token → 401。"""
    resp = await auth_client.post(
        "/api/v1/reviews", json={"code": "x = 1", "language": "python"}
    )
    assert resp.status_code == 401


async def test_reviews_rejects_invalid_token(auth_client):
    """伪造 Bearer → 401。"""
    resp = await auth_client.post(
        "/api/v1/reviews", json={"code": "x = 1", "language": "python"},
        headers={"Authorization": "Bearer garbage"},
    )
    assert resp.status_code == 401


async def test_reviews_accepts_valid_token(auth_client):
    """有效 Bearer → 200。"""
    tok = (await _issue_token(auth_client)).json()["access_token"]
    resp = await auth_client.post(
        "/api/v1/reviews", json={"code": "x = 1", "language": "python"},
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert resp.status_code == 200
