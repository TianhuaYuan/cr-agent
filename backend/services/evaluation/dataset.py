"""评测集加载（Phase 10: Task 10.1）。

评测样本结构（backend/tests/eval_samples/dataset.json）：
[
  {
    "id": "sec-001",
    "language": "python",
    "category": "security",            // security/quality/performance/structure
    "code": "源码字符串（\\n 换行）",
    "expected_findings": [
      {"severity": "high", "category": "security", "description": "...", "line": 1}
    ]
  }
]

加载为 Sample  dataclass，供 eval.py（Task 10.2）跑审查 + LLM-as-Judge 比对。
"""
from dataclasses import dataclass, field
from pathlib import Path

import json


@dataclass
class ExpectedFinding:
    severity: str  # high | medium | low | info
    category: str  # security | quality | performance | structure
    description: str
    line: int | None = None


@dataclass
class Sample:
    id: str
    language: str
    category: str
    code: str
    expected_findings: list[ExpectedFinding] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "Sample":
        ef = [ExpectedFinding(**f) for f in d.get("expected_findings", [])]
        return cls(
            id=d["id"],
            language=d["language"],
            category=d["category"],
            code=d["code"],
            expected_findings=ef,
        )


def load_dataset(path: str | Path) -> list[Sample]:
    """加载评测集 JSON → Sample 列表。"""
    path = Path(path)
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    return [Sample.from_dict(d) for d in data]
