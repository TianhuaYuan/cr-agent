"""Phase 1.3 数据模型测试（TDD: 先红）。

验证 Review / ReviewTask 两张 ORM 表与 Pydantic schemas 的行为。
使用 conftest 提供的 async_session fixture（内存 SQLite，测试间隔离）。
"""
import pytest
from sqlalchemy import select

from backend.models.review import Review
from backend.models.task import ReviewTask
from backend.schemas.review import ReviewRequest, ReviewResponse
from backend.schemas.task import TaskSchema, TaskResult


async def test_review_persist_and_query(async_session):
    """Review 能写入并读回，status 默认 pending。"""
    review = Review(code_content="x = 1", language="python")
    async_session.add(review)
    await async_session.commit()
    await async_session.refresh(review)

    assert review.id is not None
    assert review.status == "pending"
    assert review.language == "python"

    rows = (await async_session.execute(select(Review))).scalars().all()
    assert len(rows) == 1


async def test_review_task_fk_and_roles(async_session):
    """ReviewTask 关联 Review，role 枚举受控。"""
    review = Review(code_content="print(1)", language="python")
    async_session.add(review)
    await async_session.commit()
    await async_session.refresh(review)

    task = ReviewTask(review_id=review.id, role="security", status="pending")
    async_session.add(task)
    await async_session.commit()
    await async_session.refresh(task)

    assert task.review_id == review.id
    assert task.role == "security"
    # findings 字段默认空 JSON 列表
    assert task.findings == []


async def test_review_request_schema_accepts_code_and_language():
    """ReviewRequest 校验 code + language。"""
    req = ReviewRequest(code="def f(): pass", language="python")
    assert req.code == "def f(): pass"
    assert req.language == "python"


async def test_review_request_rejects_bad_language():
    """language 不在枚举内应被 Pydantic 拒绝。"""
    with pytest.raises(ValueError):
        ReviewRequest(code="x=1", language="cobol")


async def test_review_response_shape():
    """ReviewResponse 能装 review_id + status + report。"""
    resp = ReviewResponse(review_id="uuid-1", status="completed", report="# 报告")
    assert resp.review_id == "uuid-1"
    assert resp.status == "completed"
    assert "报告" in resp.report


async def test_task_schema_and_result():
    """TaskSchema / TaskResult 结构正确。"""
    schema = TaskSchema(role="quality", description="查风格", priority=2)
    assert schema.role == "quality"

    result = TaskResult(
        role="quality",
        findings=[{"severity": "low", "line": 3, "description": "命名"}],
    )
    assert result.findings[0]["severity"] == "low"
