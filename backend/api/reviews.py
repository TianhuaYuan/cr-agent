"""Review 路由（Task 6.1 + Task 1 SSE 流式）。

POST /api/v1/reviews         → 创建审查任务 + 同步执行 graph → 返回结果
POST /api/v1/reviews/stream  → SSE 流式：节点事件 + 最终 complete
GET  /api/v1/reviews/{id}    → 查询审查状态和报告
POST /api/v1/reviews/from-pr → 从 GitHub PR URL 创建审查任务
POST /api/v1/reviews/stream/from-pr → SSE 流式审查 PR

W1 简化：POST 同步执行 graph（无后台任务队列），返回时 status=completed。
W2 加 Celery/BackgroundTasks 后改为 202 + 后台异步执行。
"""
import json
import logging
import time

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import require_auth
from backend.core.common import fetch_pr_code
from backend.core.database import get_db
from backend.integrations.github import GitHubClient
from backend.models.review import Review
from backend.schemas.review import PRReviewRequest, ReviewRequest, ReviewResponse
from backend.services.supervisor.graph import build_supervisor_graph

logger = logging.getLogger(__name__)

# 受保护路由：需 Bearer token（API_AUTH_REQUIRED=True 时强制，开发态放行）。
router = APIRouter(
    prefix="/reviews",
    tags=["reviews"],
    dependencies=[Depends(require_auth)],
)


def _sse_event(event: str, data: dict) -> str:
    """构造一条 SSE 事件，填充到 ~1KB 以触发浏览器缓冲区刷出。

    填充作为 SSE 注释行（: ...）塞在事件体内，避免破坏 \n\n 事件边界。
    """
    payload = json.dumps(data, ensure_ascii=False)
    body = f"event: {event}\ndata: {payload}\n"
    need = 1024 - len(body) - 2  # ": \n\n" = 4, but body already has \n, so 3
    if need > 0:
        body += ": " + " " * need + "\n\n"
    else:
        body += "\n"
    return body


def _is_user_node(name: str) -> bool:
    """判断 langgraph 事件节点名是否为业务节点（排除框架根图 / 内部下划线节点）。"""
    if not name:
        return False
    if name == "LangGraph":
        return False
    if name.startswith("_"):
        return False
    return True


async def _create_review_record(code: str, language: str, db: AsyncSession) -> Review:
    """创建审查记录并写入数据库，返回带 id 的 Review 对象。"""
    review = Review(
        code_content=code,
        language=language,
        status="running",
    )
    db.add(review)
    await db.commit()
    await db.refresh(review)
    return review


async def _run_review_stream(
    code: str, language: str, db: AsyncSession,
    model_overrides: dict | None = None,
):
    """执行审查并流式产出 SSE 事件。

    用 graph.astream(stream_mode="updates") 替代 astream_events，
    后者在 LangGraph 1.2.7 中事件格式不稳定，导致 node_start/node_end 不触发。
    astream 直接 yield 每个节点的完成输出，更可靠。

    事件类型：
    - node_start: 节点开始执行 { "node": "<name>" }
    - node_end:   节点执行完成 { "node": "<name>" }
    - complete:   整体完成 { "review_id": "...", "report": "...", "status": "..." }
    - error:      执行异常 { "detail": "..." }
    """
    review = await _create_review_record(code, language, db)
    review_id = str(review.id)

    try:
        # 初始心跳：填充 ~1KB 刷出响应头
        yield ": heartbeat" + " " * 1000 + "\n\n"

        graph = build_supervisor_graph()
        report = ""
        workers_seen = set()
        WORKER_NAMES = {"worker_quality", "worker_security", "worker_performance", "worker_structure"}

        initial_state: dict = {"code": code, "language": language}
        if model_overrides:
            initial_state["model_overrides"] = model_overrides

        started_nodes: set[str] = set()

        async for update in graph.astream(
            initial_state,
            stream_mode="updates",
        ):
            for node_name, node_output in update.items():
                if node_name not in started_nodes:
                    yield _sse_event("node_start", {"node": node_name})
                    started_nodes.add(node_name)

                if node_name == "decompose":
                    yield _sse_event("node_end", {"node": "decompose"})
                elif node_name in WORKER_NAMES:
                    workers_seen.add(node_name)
                    yield _sse_event("node_end", {"node": node_name})
                elif node_name == "aggregate":
                    yield _sse_event("node_end", {"node": "aggregate"})
                    report = (node_output or {}).get("report", "")

        review.status = "completed"
        review.report = report
        await db.commit()

        yield _sse_event("complete", {
            "review_id": review_id,
            "report": report,
            "status": "completed",
        })

    except Exception as exc:
        logger.error("流式审查执行失败: %s", exc, exc_info=True)
        review.status = "failed"
        review.report = f"# 审查失败\n\n执行过程中发生异常：{exc}"
        await db.commit()
        yield _sse_event("error", {"detail": str(exc)})
        yield _sse_event("complete", {
            "review_id": review_id,
            "report": review.report,
            "status": "failed",
        })


@router.post("", response_model=ReviewResponse, status_code=200)
async def create_review(req: ReviewRequest, db: AsyncSession = Depends(get_db)):
    """提交代码审查。

    W1：同步执行 graph，返回 completed 结果。
    """
    review = await _create_review_record(req.code, req.language, db)

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


@router.post("/stream")
async def stream_review(req: ReviewRequest, db: AsyncSession = Depends(get_db)):
    """流式代码审查（SSE）。

    事件流：node_start → node_end → ... → complete
    Content-Type: text/event-stream
    """
    return StreamingResponse(
        _run_review_stream(req.code, req.language, db, model_overrides=req.model_overrides),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


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


async def _fetch_pr_code(pr_url: str) -> tuple[str, str]:
    """从 PR URL 拉取代码并检测语言 → (code, language)。

    失败抛 HTTPException。
    """
    try:
        return await fetch_pr_code(pr_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("拉取 PR patch 失败: %s", exc, exc_info=True)
        raise HTTPException(status_code=502, detail=f"拉取 PR 失败: {exc}")


@router.post("/from-pr", response_model=ReviewResponse, status_code=200)
async def create_review_from_pr(req: PRReviewRequest, db: AsyncSession = Depends(get_db)):
    """从 GitHub PR URL 创建代码审查（同步）。"""
    code, language = await _fetch_pr_code(req.pr_url)

    review = await _create_review_record(code, language, db)

    try:
        graph = build_supervisor_graph()
        result = await graph.ainvoke({
            "code": code,
            "language": language,
            "model_overrides": req.model_overrides,
        })
        review.status = "completed"
        review.report = result.get("report", "")
    except Exception as exc:
        logger.error("PR 审查执行失败: %s", exc, exc_info=True)
        review.status = "failed"
        review.report = f"# 审查失败\n\n执行过程中发生异常：{exc}"

    await db.commit()
    await db.refresh(review)
    return ReviewResponse.from_orm_model(review, str(review.id))


@router.post("/stream/from-pr")
async def stream_review_from_pr(req: PRReviewRequest, db: AsyncSession = Depends(get_db)):
    """从 GitHub PR URL 创建代码审查（SSE 流式）。"""
    code, language = await _fetch_pr_code(req.pr_url)

    return StreamingResponse(
        _run_review_stream(code, language, db, model_overrides=req.model_overrides),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
