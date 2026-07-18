"""Review 路由（Task 6.1）。

POST /api/v1/reviews  → 创建审查任务 + 同步执行 graph → 返回结果
GET  /api/v1/reviews/{id} → 查询审查状态和报告

W1 简化：POST 同步执行 graph（无后台任务队列），返回时 status=completed。
W2 加 Celery/BackgroundTasks 后改为 202 + 后台异步执行。
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import require_auth
from backend.core.database import get_db
from backend.models.review import Review
from backend.schemas.review import ReviewRequest, ReviewResponse
from backend.services.supervisor.graph import build_supervisor_graph

logger = logging.getLogger(__name__)

# 受保护路由：需 Bearer token（API_AUTH_REQUIRED=True 时强制，开发态放行）。
router = APIRouter(
    prefix="/reviews",
    tags=["reviews"],
    dependencies=[Depends(require_auth)],
)


@router.post("", response_model=ReviewResponse, status_code=200)
async def create_review(req: ReviewRequest, db: AsyncSession = Depends(get_db)):
    """提交代码审查。

    W1：同步执行 graph，返回 completed 结果。
    """
    review = Review(
        code_content=req.code,
        language=req.language,
        status="running",
    )
    db.add(review)
    await db.commit()
    await db.refresh(review)

    # 同步执行 graph（W1 简化，W2 改 BackgroundTasks）
    try:
        graph = build_supervisor_graph()
        result = await graph.ainvoke({
            "code": req.code,
            "language": req.language,
        })
        review.status = "completed"
        review.report = result.get("report", "")
    except Exception as exc:
        logger.error("审查执行失败: %s", exc, exc_info=True)
        review.status = "failed"
        review.report = f"# 审查失败\n\n执行过程中发生异常：{exc}"

    await db.commit()
    await db.refresh(review)
    return ReviewResponse.from_orm_model(review, str(review.id))


@router.get("/{review_id}", response_model=ReviewResponse)
async def get_review(review_id: str, db: AsyncSession = Depends(get_db)):
    """查询审查结果。"""
    try:
        rid = int(review_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="审查任务不存在")

    result = await db.execute(select(Review).where(Review.id == rid))
    review = result.scalar_one_or_none()
    if not review:
        raise HTTPException(status_code=404, detail="审查任务不存在")
    return ReviewResponse.from_orm_model(review, str(review.id))
