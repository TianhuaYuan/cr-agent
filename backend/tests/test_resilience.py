"""Phase 5 Resilience 测试（TDD RED → GREEN）。

覆盖三个容错机制：
- Task 5.1 max_iterations 熔断：iteration_count 超限 → 跳过 Workers 直达 aggregate
- Task 5.2 Worker 超时：_call_llm > timeout → 降级 info finding，不抛、不阻塞其他 Worker
- Task 5.3 Worker 异常不阻塞：异常 → 记录 state.errors → 报告"审查警告"区标注
"""
import asyncio
import json
from types import SimpleNamespace

import pytest

from backend.services.supervisor.graph import build_supervisor_graph
from backend.services.workers.base import BaseWorker
from backend.services.workers.quality import QualityWorker


# ── Task 5.1: max_iterations 熔断 ──────────────────────────────────────────

class TestMaxIterationsCircuitBreaker:
    """iteration_count > max_iterations → decompose 后跳过 Workers，直达 aggregate。"""

    async def test_circuit_breaker_skips_workers(self, monkeypatch, fake_llm_factory):
        """max_iterations=0 → decompose 后 iteration_count=1 > 0 → 熔断，worker_results 空。"""
        # decompose 用正常 JSON 避免降级干扰
        client = fake_llm_factory(
            json.dumps([{"role": "security", "description": "x", "priority": 1}])
        )
        monkeypatch.setattr("backend.core.llm.get_chat_client", lambda: client)

        graph = build_supervisor_graph()
        result = await graph.ainvoke({
            "code": "x = 1",
            "language": "python",
            "max_iterations": 0,  # 熔断阈值设 0，decompose 后 iteration_count=1 > 0
        })

        # Workers 被跳过
        worker_results = result.get("worker_results", [])
        assert worker_results == [], f"熔断后 worker_results 应为空，实际 {len(worker_results)}"

        # 报告仍有产出（aggregate 跑了）
        report = result.get("report", "")
        assert report, "熔断后仍应有报告"

        # 报告含熔断警告
        assert "熔断" in report or "最大迭代" in report, "报告应标注熔断"

    async def test_normal_flow_when_under_limit(self, monkeypatch, fake_llm_factory):
        """max_iterations=3（默认）→ 正常走 Workers，worker_results 非空。"""
        client = fake_llm_factory("not json")  # 触发 decompose 降级 + worker 降级
        monkeypatch.setattr("backend.core.llm.get_chat_client", lambda: client)

        graph = build_supervisor_graph()
        result = await graph.ainvoke({
            "code": "x = 1",
            "language": "python",
            "max_iterations": 3,
        })

        worker_results = result.get("worker_results", [])
        assert len(worker_results) > 0, "未熔断时 Workers 应执行"


# ── Task 5.2: Worker 超时 ──────────────────────────────────────────────────

class _SlowFakeClient:
    """慢客户端：create() 里 sleep，模拟 LLM 超时。"""

    def __init__(self, delay: float = 1.0, response_text: str = "[]"):
        self._delay = delay
        self._text = response_text

    @property
    def chat(self):
        async def _create(*args, **kwargs):
            await asyncio.sleep(self._delay)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=self._text))]
            )
        return SimpleNamespace(completions=SimpleNamespace(create=_create))


class TestWorkerTimeout:
    """_call_llm 超时 → review() 降级返回 info finding，不抛。"""

    async def test_timeout_returns_degraded_finding(self, monkeypatch):
        """慢客户端 + timeout=0.01 → 1 条 info finding，description 含 timeout。"""
        client = _SlowFakeClient(delay=1.0)
        monkeypatch.setattr("backend.core.llm.get_chat_client", lambda: client)

        worker = QualityWorker()
        worker.timeout = 0.01  # 测试用极小超时
        findings = await worker.review("x = 1", "python")

        assert len(findings) == 1
        assert findings[0]["severity"] == "info"
        desc = findings[0]["description"].lower()
        assert "timeout" in desc or "超时" in findings[0]["description"], \
            f"降级 finding 应标注超时，实际: {findings[0]['description']}"

    async def test_timeout_does_not_raise(self, monkeypatch):
        """超时不应抛异常（被 review 内部捕获）。"""
        client = _SlowFakeClient(delay=2.0)
        monkeypatch.setattr("backend.core.llm.get_chat_client", lambda: client)

        worker = QualityWorker()
        worker.timeout = 0.05
        # 不应 raise
        findings = await worker.review("x = 1", "python")
        assert isinstance(findings, list)

    async def test_timeout_does_not_block_others(self, monkeypatch):
        """一个慢 Worker 不影响其他 Worker 的结果聚合。"""
        # 用两个不同客户端：quality 慢，其他正常
        normal_client = fake_llm_factory_client(
            json.dumps([{"severity": "low", "line": 1, "description": "ok"}])
        )
        slow_client = _SlowFakeClient(delay=1.0)

        call_count = {"n": 0}

        class _RoutingClient:
            """第 1 次调用（decompose）走 normal，后续 worker 调用按 role 路由。"""
            @property
            def chat(self):
                async def _create(*args, **kwargs):
                    call_count["n"] += 1
                    # decompose 是第 1 次
                    if call_count["n"] == 1:
                        return await normal_client.chat.completions.create(*args, **kwargs)
                    # 后续 worker 调用：quality 慢，其他快
                    messages = kwargs.get("messages", [])
                    sys_content = ""
                    for m in messages:
                        if m.get("role") == "system":
                            sys_content = m.get("content", "")
                    if "质量" in sys_content or "quality" in sys_content.lower():
                        return await slow_client.chat.completions.create(*args, **kwargs)
                    return await normal_client.chat.completions.create(*args, **kwargs)
                return SimpleNamespace(completions=SimpleNamespace(create=_create))

        monkeypatch.setattr("backend.core.llm.get_chat_client", lambda: _RoutingClient())

        # 给 quality worker 设短超时，避免测试卡 1s
        from backend.services.supervisor import graph as graph_mod
        original_workers = dict(graph_mod._WORKERS)
        graph_mod._WORKERS["quality"].timeout = 0.01
        try:
            g = build_supervisor_graph()
            result = await g.ainvoke({"code": "x=1", "language": "python"})
        finally:
            graph_mod._WORKERS["quality"].timeout = 30.0

        worker_results = result.get("worker_results", [])
        # quality 超时降级为 1 条 info，其他 3 个 worker 各有 1 条 low → 共 ≥4
        assert len(worker_results) >= 4, \
            f"超时不应阻塞其他 Worker，worker_results 应 ≥4，实际 {len(worker_results)}"


# ── Task 5.3: Worker 异常不阻塞 ────────────────────────────────────────────

class TestWorkerExceptionNoBlock:
    """Worker 异常 → 捕获 → 记录 state.errors → graph 继续 → 报告含审查警告。"""

    async def test_exception_recorded_to_errors(self, monkeypatch):
        """所有 Worker 的 LLM 都抛异常 → state.errors 有记录，报告含审查警告。"""

        class _BoomClient:
            @property
            def chat(self):
                raise RuntimeError("network down")

        monkeypatch.setattr("backend.core.llm.get_chat_client", lambda: _BoomClient())

        graph = build_supervisor_graph()
        result = await graph.ainvoke({"code": "x = 1", "language": "python"})

        errors = result.get("errors", [])
        assert len(errors) > 0, "Worker 异常应记录到 state.errors"

        report = result.get("report", "")
        assert "审查警告" in report or "⚠️" in report, "报告应含审查警告区"

    async def test_partial_failure_still_produces_report(self, monkeypatch):
        """部分 Worker 异常 → 报告仍生成，含异常标注 + 正常维度。"""
        call_count = {"n": 0}

        class _MixedClient:
            """decompose 正常；security worker 抛异常，其他正常。"""
            _FINDINGS = json.dumps([
                {"severity": "low", "line": 1, "description": "minor", "suggestion": "fix"}
            ])

            @property
            def chat(self):
                async def _create(*args, **kwargs):
                    call_count["n"] += 1
                    if call_count["n"] == 1:
                        # decompose
                        return SimpleNamespace(choices=[
                            SimpleNamespace(message=SimpleNamespace(
                                content=json.dumps([{"role": "security", "description": "x", "priority": 1}])
                            ))
                        ])
                    messages = kwargs.get("messages", [])
                    sys_content = ""
                    for m in messages:
                        if m.get("role") == "system":
                            sys_content = m.get("content", "")
                    if "安全" in sys_content or "security" in sys_content.lower():
                        raise RuntimeError("security worker boom")
                    return SimpleNamespace(choices=[
                        SimpleNamespace(message=SimpleNamespace(content=self._FINDINGS))
                    ])
                return SimpleNamespace(completions=SimpleNamespace(create=_create))

        monkeypatch.setattr("backend.core.llm.get_chat_client", lambda: _MixedClient())

        graph = build_supervisor_graph()
        result = await graph.ainvoke({"code": "x = 1", "language": "python"})

        report = result.get("report", "")
        assert report, "部分失败仍应生成报告"
        assert "审查警告" in report or "⚠️" in report, "报告应含异常警告"

        errors = result.get("errors", [])
        assert any("security" in str(e).lower() or "异常" in str(e) for e in errors), \
            "errors 应含 security worker 的异常记录"


# ── helper ─────────────────────────────────────────────────────────────────

def fake_llm_factory_client(response_text: str):
    """从 fake_llm_factory 模式构造的独立假客户端。"""
    class _Fake:
        @property
        def chat(self):
            async def _create(*args, **kwargs):
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content=response_text))]
                )
            return SimpleNamespace(completions=SimpleNamespace(create=_create))
    return _Fake()
