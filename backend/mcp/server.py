"""MCP Gateway Server — 把代码审查能力封装为 MCP Tools。

W2 Phase 8: 用 FastMCP 把 W1 的 4 个核心能力暴露为标准 MCP 工具，
外部客户端（Claude Desktop / GitHub Actions / 其他 Agent）可通过 MCP 协议调用。

设计决策（面试可讲）：
- **统一入口**：所有审查能力通过 MCP Server 统一暴露，外部客户端不需要知道
  LangGraph / Worker / Aggregator 的内部实现，只需调 MCP Tool。
- **Tool 粒度**：4 个 Tool 对应 4 个能力层级——完整审查 / 任务拆解 / 单 Worker / 聚合报告。
  粗粒度（review_code）面向终端用户，细粒度（worker_review）面向编排层。
- **复用 W1 引擎**：Tool 内部调 W1 的 build_supervisor_graph() / Worker / Aggregator，
  不重写审查逻辑。MCP 是"壳"，引擎是"核"。
"""
import logging
from datetime import datetime, timezone

from fastmcp import FastMCP
from sqlalchemy import func, select

from backend.core.database import AsyncSessionLocal
from backend.models.review import Review
from backend.services.supervisor.graph import build_supervisor_graph
from backend.services.supervisor.decompose import decompose_node
from backend.services.workers.registry import WORKERS as _WORKERS
from backend.services.aggregator.merge import aggregate_findings
from backend.services.aggregator.report import generate_report

logger = logging.getLogger(__name__)

# ── MCP Server 实例 ──────────────────────────────────────────

mcp = FastMCP("cr-agent")

# Worker 实例映射（复用 registry 单一来源）


# ── Tool 1: ping（健康检查）──────────────────────────────────


@mcp.tool()
def ping() -> dict:
    """健康检查，返回 {'pong': True}。"""
    return {"pong": True}


# ── Tool 2: review_code（完整审查）───────────────────────────


@mcp.tool()
async def review_code(code: str, language: str = "python") -> str:
    """完整代码审查：decompose → 4 Worker 并行 → aggregate → Markdown 报告。

    Args:
        code: 要审查的源代码字符串。
        language: 代码语言（python / javascript / typescript / go / java），默认 python。

    Returns:
        Markdown 格式的审查报告字符串。
    """
    logger.info("MCP review_code: language=%s, code_len=%d", language, len(code))
    graph = build_supervisor_graph()
    result = await graph.ainvoke({
        "code": code,
        "language": language,
        "iteration_count": 0,
        "max_iterations": 3,
    })
    report = result.get("report", "")
    logger.info("MCP review_code done: report_len=%d", len(report))
    return report


# ── Tool 3: decompose_code（任务拆解）────────────────────────


@mcp.tool()
async def decompose_code(code: str, language: str = "python") -> list:
    """把代码审查拆解为子任务列表。

    Args:
        code: 要审查的源代码字符串。
        language: 代码语言，默认 python。

    Returns:
        子任务列表，每项形如 {"role": "...", "description": "...", "priority": N}。
    """
    logger.info("MCP decompose_code: language=%s", language)
    state = {
        "code": code,
        "language": language,
        "iteration_count": 0,
        "max_iterations": 3,
    }
    result = await decompose_node(state)
    tasks = result.get("tasks", [])
    logger.info("MCP decompose_code done: %d tasks", len(tasks))
    return tasks


# ── Tool 4: worker_review（单 Worker 审查）───────────────────


@mcp.tool()
async def worker_review(code: str, language: str, role: str) -> list:
    """指定单个 Worker 审查代码，返回该维度的 findings。

    Args:
        code: 要审查的源代码字符串。
        language: 代码语言。
        role: Worker 角色（security / quality / performance / structure）。

    Returns:
        findings 列表，每项含 severity / line / description / suggestion / code_snippet。
    """
    logger.info("MCP worker_review: role=%s, language=%s", role, language)
    worker = _WORKERS.get(role)
    if not worker:
        logger.warning("MCP worker_review: 未知 role=%s", role)
        return [{
            "severity": "info",
            "line": None,
            "description": f"未知 Worker 角色: {role}，可选: {list(_WORKERS.keys())}",
            "suggestion": "请使用 security / quality / performance / structure",
            "code_snippet": "",
            "worker": role,
        }]
    findings = await worker.review(code, language)
    logger.info("MCP worker_review done: role=%s, %d findings", role, len(findings))
    return findings


# ── Tool 5: aggregate_report（聚合报告）──────────────────────


@mcp.tool()
def aggregate_report(findings: list, language: str = "python") -> str:
    """把多个 Worker 的 findings 聚合去重，生成 Markdown 报告。

    Args:
        findings: 所有 Worker 的 findings 列表（合并后传入）。
        language: 代码语言，用于报告头部标注。

    Returns:
        Markdown 格式的审查报告字符串。
    """
    logger.info("MCP aggregate_report: %d findings, language=%s", len(findings), language)
    deduped = aggregate_findings(findings)
    report = generate_report(deduped, language=language)
    logger.info("MCP aggregate_report done: %d deduped → report_len=%d",
                len(deduped), len(report))
    return report


# ── Resource 1: review://history（最近审查记录）───────────────


@mcp.resource("review://history")
async def review_history() -> list:
    """返回最近 10 条审查记录（id / 语言 / 状态 / 创建时间）。

    Returns:
        审查记录列表，每项含 id / language / status / created_at。
    """
    logger.info("MCP resource: review://history")
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Review)
            .order_by(Review.created_at.desc())
            .limit(10)
        )
        reviews = result.scalars().all()
        return [
            {
                "id": r.id,
                "language": r.language,
                "status": r.status,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in reviews
        ]


# ── Resource 2: review://stats（审查统计）────────────────────


@mcp.resource("review://stats")
async def review_stats() -> dict:
    """返回审查统计信息（总数 / 各状态数量）。

    Returns:
        统计字典，含 total / pending / running / completed / failed。
    """
    logger.info("MCP resource: review://stats")
    async with AsyncSessionLocal() as session:
        total_result = await session.execute(select(func.count(Review.id)))
        total = total_result.scalar() or 0

        status_result = await session.execute(
            select(Review.status, func.count(Review.id))
            .group_by(Review.status)
        )
        status_counts = {row[0]: row[1] for row in status_result}

        return {
            "total": total,
            "pending": status_counts.get("pending", 0),
            "running": status_counts.get("running", 0),
            "completed": status_counts.get("completed", 0),
            "failed": status_counts.get("failed", 0),
        }
