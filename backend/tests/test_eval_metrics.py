"""硬指标 precision/recall/F1 测试（W3: Task 11.2）。

TDD Red → Green：
- Red：backend.services.evaluation.metrics.compute_prf 不存在 → import 失败。
- Green：实现 desc/line 贪心匹配 + 空集约定，让测试通过。

同时验证 run_one 返回 prf，summarize 聚合 prf_avg。
"""
import json
from types import SimpleNamespace

import pytest

from backend.services.evaluation.dataset import Sample, ExpectedFinding
from backend.services.evaluation.eval import run_one, run_samples, summarize
from backend.services.evaluation.metrics import compute_prf


def test_perfect_match():
    exp = [
        {"description": "硬编码 API 密钥", "line": 1},
        {"description": "SQL 注入风险", "line": 2},
    ]
    act = [
        {"description": "硬编码 API 密钥", "line": 1},
        {"description": "SQL 注入风险", "line": 2},
    ]
    r = compute_prf(exp, act)
    assert r["precision"] == 1.0 and r["recall"] == 1.0 and r["f1"] == 1.0
    assert r["tp"] == 2 and r["fp"] == 0 and r["fn"] == 0


def test_empty_actual_recall_zero():
    exp = [{"description": "硬编码 API 密钥", "line": 1}]
    r = compute_prf(exp, [])
    assert r["recall"] == 0.0
    assert r["precision"] == 1.0


def test_empty_expected_precision_one():
    r = compute_prf([], [{"description": "无关发现", "line": 5}])
    assert r["precision"] == 1.0 and r["recall"] == 1.0 and r["f1"] == 1.0


def test_partial_match_recall_half():
    exp = [
        {"description": "硬编码 API 密钥", "line": 1},
        {"description": "SQL 注入风险", "line": 2},
    ]
    act = [{"description": "硬编码 API 密钥", "line": 1}]  # 只命中 1/2
    r = compute_prf(exp, act)
    assert r["recall"] == 0.5
    assert r["precision"] == 1.0  # 1 TP, 0 FP
    assert abs(r["f1"] - 0.6667) < 0.01


def test_false_positive_lowers_precision():
    exp = [{"description": "硬编码 API 密钥", "line": 1}]
    act = [
        {"description": "硬编码 API 密钥", "line": 1},
        {"description": "无关发现", "line": 5},  # FP
    ]
    r = compute_prf(exp, act)
    assert r["recall"] == 1.0
    assert r["precision"] == 0.5  # 1 TP, 1 FP


def test_line_match_counts():
    # desc 不同但 line 相同也算命中（行号是更强信号）
    exp = [{"description": "硬编码密钥", "line": 1}]
    act = [{"description": "硬编码 API 密钥和数据库密码", "line": 1}]
    r = compute_prf(exp, act)
    assert r["tp"] == 1 and r["recall"] == 1.0


class _FakeGraphClient:
    _FINDINGS = json.dumps([
        {"severity": "high", "line": 1, "description": "硬编码 API 密钥和数据库密码",
         "suggestion": "x", "code_snippet": "API_KEY='...'"},
    ])

    @property
    def chat(self):
        async def _create(*a, **k):
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=self._FINDINGS))]
            )

        return SimpleNamespace(completions=SimpleNamespace(create=_create))


class _FakeJudgeClient:
    _JUDGE = json.dumps({"completeness": 0.9, "accuracy": 0.8, "source_traceability": 1.0, "rationale": "ok"})

    @property
    def chat(self):
        async def _create(*a, **k):
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=self._JUDGE))]
            )

        return SimpleNamespace(completions=SimpleNamespace(create=_create))


def _samples():
    return [Sample(
        id="sec-001", language="python", category="security", code="API_KEY='x'",
        expected_findings=[ExpectedFinding("high", "security", "硬编码 API 密钥和数据库密码", 1)],
    )]


@pytest.mark.asyncio
async def test_run_one_returns_prf(monkeypatch):
    monkeypatch.setattr("backend.core.llm.get_chat_client", lambda: _FakeGraphClient())
    r = await run_one(_samples()[0], judge_client=_FakeJudgeClient())
    assert "prf" in r
    assert r["prf"]["tp"] >= 1  # 实际发现包含期望的硬编码密钥


@pytest.mark.asyncio
async def test_summarize_aggregates_prf(monkeypatch):
    monkeypatch.setattr("backend.core.llm.get_chat_client", lambda: _FakeGraphClient())
    results = await run_samples(_samples(), judge_client=_FakeJudgeClient())
    s = summarize(results)
    assert s["prf_avg"] is not None
    assert s["prf_avg"]["recall"] >= 0.5
