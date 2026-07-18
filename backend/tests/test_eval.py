"""LLM-as-Judge 评测测试（Phase 10: Task 10.2）。

TDD Red → Green：
- 先写测试（Red）：backend.services.evaluation.judge / eval 不存在 → import 失败。
- 再写实现（Green）：让测试通过。

测试策略：
- 注入 _FakeGraphClient（graph 审查用 LLM）与 _FakeJudgeClient（裁判 LLM），零真实 API。
- 验证 judge 解析、规则基线、LLM 裁判、run_one 端到端（graph + judge）。
"""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.services.evaluation.dataset import load_dataset
from backend.services.evaluation.judge import (
    Judgment,
    _parse_judge_json,
    judge_rule_based,
    judge_with_llm,
)


class _FakeGraphClient:
    """graph 审查用的假 LLM（返回 worker findings JSON）。"""

    _FINDINGS = json.dumps([
        {
            "severity": "high",
            "line": 1,
            "description": "硬编码 API 密钥和数据库密码",
            "suggestion": "改用环境变量",
            "code_snippet": "API_KEY='...'",
        }
    ])

    @property
    def chat(self):
        async def _create(*a, **k):
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=self._FINDINGS))]
            )

        return SimpleNamespace(completions=SimpleNamespace(create=_create))


class _FakeJudgeClient:
    """裁判 LLM 假客户端（返回评委 JSON）。"""

    _JUDGE = json.dumps({
        "completeness": 0.9,
        "accuracy": 0.8,
        "source_traceability": 1.0,
        "rationale": "覆盖了主要安全问题，来源标注清晰",
    })

    @property
    def chat(self):
        async def _create(*a, **k):
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=self._JUDGE))]
            )

        return SimpleNamespace(completions=SimpleNamespace(create=_create))


def _patch_graph_llm(monkeypatch):
    monkeypatch.setattr("backend.core.llm.get_chat_client", lambda: _FakeGraphClient())


def test_parse_judge_json_strips_fence():
    text = "```json\n" + json.dumps(
        {"completeness": 0.5, "accuracy": 0.5, "source_traceability": 0.5}
    ) + "\n```"
    d = _parse_judge_json(text)
    assert d["completeness"] == 0.5


def test_judge_rule_based():
    expected = [
        {"severity": "high", "category": "security", "description": "硬编码 API 密钥和数据库密码", "line": 1}
    ]
    report = "硬编码 API 密钥和数据库密码\n行号 1"
    j = judge_rule_based(expected, report)
    assert isinstance(j, Judgment)
    assert j.completeness > 0.5
    assert j.source_traceability == 1.0


@pytest.mark.asyncio
async def test_judge_with_llm(monkeypatch):
    monkeypatch.setattr("backend.core.llm.get_chat_client", lambda: _FakeJudgeClient())
    j = await judge_with_llm("code", [{"description": "x"}], "report")
    assert isinstance(j, Judgment)
    # 0.4*0.9 + 0.4*0.8 + 0.2*1.0 = 0.88
    assert abs(j.composite - 0.88) < 0.01


@pytest.mark.asyncio
async def test_run_one(monkeypatch):
    _patch_graph_llm(monkeypatch)
    from backend.services.evaluation.eval import run_one

    samples = load_dataset(Path(__file__).parent / "eval_samples" / "dataset.json")
    r = await run_one(samples[0], judge_client=_FakeJudgeClient())
    assert r["id"] == samples[0].id
    assert "judgment" in r
    assert r["judgment"]["composite"] > 0
