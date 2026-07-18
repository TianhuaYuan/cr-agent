"""全量评测 + 分类聚合报告测试（W3: Task 11.1）。

TDD Red → Green：
- Red：backend.services.evaluation.eval 尚无 summarize_by_category / render_report / run_samples → import 失败。
- Green：实现聚合与报告渲染，让测试通过。

测试策略：
- 注入 _FakeGraphClient（graph 审查用 LLM，返回 2 条 findings）与 _FakeJudgeClient（裁判 LLM）。
- 验证 run_one 返回 findings、summarize_by_category 按类聚合、render_report 渲染关键段落。
"""
import json
from types import SimpleNamespace

import pytest

from backend.services.evaluation.dataset import Sample, ExpectedFinding
from backend.services.evaluation.eval import run_one, run_samples, summarize, summarize_by_category, render_report


class _FakeGraphClient:
    """graph 审查用的假 LLM。

    decompose 期望 task 列表（role + description），worker 期望 finding 列表。
    用不同 prompt 返回不同 JSON——按 messages 内容区分调用方。
    """

    _TASKS = json.dumps([
        {"role": "security", "description": "审查安全"},
        {"role": "quality", "description": "审查质量"},
        {"role": "performance", "description": "审查性能"},
        {"role": "structure", "description": "审查结构"},
    ])
    _FINDINGS = json.dumps([
        {
            "severity": "high",
            "line": 1,
            "description": "硬编码 API 密钥和数据库密码",
            "suggestion": "改用环境变量",
            "code_snippet": "API_KEY='...'",
        },
        {
            "severity": "medium",
            "line": 3,
            "description": "缺少输入校验",
            "suggestion": "加类型检查",
            "code_snippet": "x = data",
        },
    ])

    @property
    def chat(self):
        findings = self._FINDINGS

        async def _create(*a, **k):
            # decompose 的 prompt 含「任务」，worker 的 prompt 含「finding」
            msgs = k.get("messages") or (a[0] if a else None)
            text = ""
            if msgs:
                text = msgs[-1].get("content", "") if isinstance(msgs, list) else ""
            content = self._TASKS if "任务" in text or "task" in text.lower() else findings
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
            )

        return SimpleNamespace(completions=SimpleNamespace(create=_create))


class _FakeJudgeClient:
    """裁判 LLM 假客户端。"""

    _JUDGE = json.dumps({
        "completeness": 0.9,
        "accuracy": 0.8,
        "source_traceability": 1.0,
        "rationale": "覆盖了主要问题",
    })

    @property
    def chat(self):
        async def _create(*a, **k):
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=self._JUDGE))]
            )

        return SimpleNamespace(completions=SimpleNamespace(create=_create))


def _samples() -> list[Sample]:
    return [
        Sample(
            id="sec-001", language="python", category="security", code="API_KEY='x'",
            expected_findings=[ExpectedFinding("high", "security", "硬编码 API 密钥和数据库密码", 1)],
        ),
        Sample(
            id="sec-002", language="python", category="security", code="y=2",
            expected_findings=[ExpectedFinding("high", "security", "SQL 注入风险", 2)],
        ),
        Sample(
            id="q-001", language="python", category="quality", code="z=3",
            expected_findings=[ExpectedFinding("medium", "quality", "缺少输入校验", 3)],
        ),
    ]


@pytest.mark.asyncio
async def test_run_one_returns_findings(monkeypatch):
    monkeypatch.setattr("backend.core.llm.get_chat_client", lambda: _FakeGraphClient())
    r = await run_one(_samples()[0], judge_client=_FakeJudgeClient())
    assert r["id"] == "sec-001"
    assert "judgment" in r and r["judgment"]["composite"] > 0
    assert "findings" in r and len(r["findings"]) == 2  # 4 Worker × 2 findings 去重后 = 2


@pytest.mark.asyncio
async def test_run_samples_runs_all(monkeypatch):
    monkeypatch.setattr("backend.core.llm.get_chat_client", lambda: _FakeGraphClient())
    results = await run_samples(_samples(), judge_client=_FakeJudgeClient())
    assert len(results) == 3
    assert all("judgment" in r for r in results)


def test_summarize_by_category():
    results = [
        {"id": "sec-001", "category": "security",
         "judgment": {"composite": 0.9, "completeness": 0.9, "accuracy": 0.8, "source_traceability": 1.0}},
        {"id": "sec-002", "category": "security",
         "judgment": {"composite": 0.7, "completeness": 0.7, "accuracy": 0.7, "source_traceability": 0.7}},
        {"id": "q-001", "category": "quality",
         "judgment": {"composite": 0.8, "completeness": 0.8, "accuracy": 0.8, "source_traceability": 0.8}},
    ]
    by_cat = summarize_by_category(results)
    assert set(by_cat.keys()) == {"security", "quality"}
    assert by_cat["security"]["count"] == 2
    assert abs(by_cat["security"]["composite_avg"] - 0.8) < 1e-9
    assert abs(by_cat["quality"]["composite_avg"] - 0.8) < 1e-9


def test_summarize_aggregates_overall():
    results = [
        {"id": "a", "category": "security",
         "judgment": {"composite": 0.9, "completeness": 0.9, "accuracy": 0.8, "source_traceability": 1.0}},
        {"id": "b", "category": "quality",
         "judgment": {"composite": 0.7, "completeness": 0.7, "accuracy": 0.7, "source_traceability": 0.7}},
    ]
    s = summarize(results)
    assert abs(s["composite_avg"] - 0.8) < 1e-9
    assert s["total"] == 2
    assert "by_category" in s


def test_render_report_contains_sections():
    results = [
        {"id": "sec-001", "category": "security",
         "judgment": {"composite": 0.9, "completeness": 0.9, "accuracy": 0.8, "source_traceability": 1.0},
         "findings": [{"description": "硬编码密钥"}], "report": "# 审查报告\n硬编码密钥"},
        {"id": "q-001", "category": "quality",
         "judgment": {"composite": 0.7, "completeness": 0.7, "accuracy": 0.7, "source_traceability": 0.7},
         "findings": [], "report": "# 审查报告\n风格问题"},
    ]
    s = summarize(results)
    md = render_report(s)
    assert "总览" in md
    assert "security" in md and "quality" in md
    assert "sec-001" in md and "q-001" in md
    assert "composite_avg" in md or "composite" in md
