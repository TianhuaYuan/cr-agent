"""Task 17.1: GET /api/v1/models 端点测试（TDD RED → GREEN）。

覆盖：
- 端点存在，返回 200
- 返回结构含 6 个 key：decompose / worker.quality / worker.security / worker.performance / worker.structure / judge
- 每个 key 的值是当前配置的 model 名称
- 端点不需要鉴权（只暴露 model 名，无敏感信息）
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


class TestModelsAPI:
    async def test_models_endpoint_exists(self, api_client):
        """GET /api/v1/models 端点存在，返回 200。"""
        resp = await api_client.get("/api/v1/models")
        assert resp.status_code == 200

    async def test_models_endpoint_returns_six_keys(self, api_client):
        """返回结构含 6 个角色 key。"""
        resp = await api_client.get("/api/v1/models")
        data = resp.json()
        expected_keys = {
            "decompose",
            "worker.quality",
            "worker.security",
            "worker.performance",
            "worker.structure",
            "judge",
        }
        assert set(data.keys()) == expected_keys, (
            f"期望 6 个 key: {expected_keys}, 实际: {set(data.keys())}"
        )

    async def test_models_endpoint_returns_non_empty_values(self, api_client):
        """每个 key 的值是非空字符串（当前配置的 model 名称）。"""
        resp = await api_client.get("/api/v1/models")
        data = resp.json()
        for key, value in data.items():
            assert isinstance(value, str), f"{key} 的值应该是字符串"
            assert len(value) > 0, f"{key} 的值不应该为空"

    async def test_models_endpoint_no_auth_required(self, api_client):
        """端点不需要鉴权（无 Authorization header 也能访问）。"""
        resp = await api_client.get("/api/v1/models")
        assert resp.status_code == 200
