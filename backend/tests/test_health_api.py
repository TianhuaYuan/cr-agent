"""Task 18.3: 健康检查端点测试。

覆盖：
- 端点存在，返回 200
- 返回结构含 status / version / db
- 不需要鉴权
- DB 正常时 db="ok"
"""
import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.core.database import Base, get_db


@pytest_asyncio.fixture
async def api_client():
    """API 测试客户端：内存 DB + httpx。"""
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

    from backend.main import create_app

    app = create_app()
    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


class TestHealthAPI:
    async def test_health_endpoint_exists(self, api_client):
        """GET /api/v1/health 端点存在，返回 200。"""
        resp = await api_client.get("/api/v1/health")
        assert resp.status_code == 200

    async def test_health_returns_expected_keys(self, api_client):
        """返回结构含 status / version / db。"""
        resp = await api_client.get("/api/v1/health")
        data = resp.json()
        expected_keys = {"status", "version", "db"}
        assert set(data.keys()) == expected_keys, (
            f"期望 key: {expected_keys}, 实际: {set(data.keys())}"
        )

    async def test_health_db_is_ok(self, api_client):
        """数据库正常时 db="ok"。"""
        resp = await api_client.get("/api/v1/health")
        data = resp.json()
        assert data["db"] == "ok"
        assert data["status"] == "ok"

    async def test_health_no_auth_required(self, api_client):
        """不需要鉴权。"""
        resp = await api_client.get("/api/v1/health")
        assert resp.status_code == 200
