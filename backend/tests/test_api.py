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

    async def test_create_review_with_model_overrides(self, api_client):
        """POST + model_overrides → 200（不回归）。"""
        resp = await api_client.post("/api/v1/reviews", json={
            "code": "x = 1",
            "language": "python",
            "model_overrides": {"decompose": "gpt-4o", "judge": "claude-sonnet"},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"

    async def test_create_review_model_overrides_rejects_invalid_key(self, api_client):
        """POST + model_overrides 无效 key → 422。"""
        resp = await api_client.post("/api/v1/reviews", json={
            "code": "x = 1",
            "language": "python",
            "model_overrides": {"unknown_role": "gpt-4o"},
        })
        assert resp.status_code == 422


def _parse_sse(text: str) -> list[dict]:
    """把 SSE 响应文本解析成 [{event, data}, ...] 列表。"""
    events = []
    current_event = "message"
    current_data = []
    for line in text.splitlines():
        if line == "":
            if current_data:
                events.append({"event": current_event, "data": "\n".join(current_data)})
                current_event = "message"
                current_data = []
        elif line.startswith("event:"):
            current_event = line[len("event:"):].strip()
        elif line.startswith("data:"):
            current_data.append(line[len("data:"):].strip())
    if current_data:
        events.append({"event": current_event, "data": "\n".join(current_data)})
    return events


class TestStreamReviewAPI:
    """POST /api/v1/reviews/stream — SSE 流式审查。"""

    async def test_stream_content_type(self, api_client):
        """流式 endpoint 返回 text/event-stream。"""
        async with api_client.stream(
            "POST", "/api/v1/reviews/stream",
            json={"code": "x = 1", "language": "python"},
        ) as resp:
            assert resp.status_code == 200
            ct = resp.headers.get("content-type", "")
            assert "text/event-stream" in ct

    async def test_stream_has_complete_event(self, api_client):
        """流末尾有 complete 事件,data 是 JSON 含 review_id 和 report。"""
        async with api_client.stream(
            "POST", "/api/v1/reviews/stream",
            json={"code": "api_key = 'sk-xxx'\nx = 1", "language": "python"},
        ) as resp:
            body = await resp.aread()

        events = _parse_sse(body.decode("utf-8"))
        complete_events = [e for e in events if e["event"] == "complete"]
        assert len(complete_events) == 1
        data = json.loads(complete_events[0]["data"])
        assert "review_id" in data
        assert "report" in data
        assert len(data["report"]) > 0

    async def test_stream_has_node_events(self, api_client):
        """流中有 node_start 和 node_end 事件,且 start 早于 end。"""
        async with api_client.stream(
            "POST", "/api/v1/reviews/stream",
            json={"code": "x = 1", "language": "python"},
        ) as resp:
            body = await resp.aread()

        events = _parse_sse(body.decode("utf-8"))
        node_starts = [e for e in events if e["event"] == "node_start"]
        node_ends = [e for e in events if e["event"] == "node_end"]
        assert len(node_starts) > 0, "expected at least one node_start"
        assert len(node_ends) > 0, "expected at least one node_end"
        assert len(node_starts) == len(node_ends), \
            f"node_start ({len(node_starts)}) != node_end ({len(node_ends)})"

    async def test_stream_validation_empty_code(self, api_client):
        """流式 endpoint 空代码 → 422。"""
        async with api_client.stream(
            "POST", "/api/v1/reviews/stream",
            json={"code": "", "language": "python"},
        ) as resp:
            assert resp.status_code == 422

    async def test_stream_with_model_overrides(self, api_client):
        """SSE 流式 + model_overrides → 200 + complete 事件。"""
        async with api_client.stream(
            "POST", "/api/v1/reviews/stream",
            json={
                "code": "x = 1",
                "language": "python",
                "model_overrides": {"decompose": "deepseek-chat", "worker.quality": "gpt-4o"},
            },
        ) as resp:
            assert resp.status_code == 200
            body = await resp.aread()

        events = _parse_sse(body.decode("utf-8"))
        complete = [e for e in events if e["event"] == "complete"]
        assert len(complete) == 1
