"""评测集加载测试（Phase 10: Task 10.1）。

TDD Red → Green：
- 先写测试（Red）：backend.services.evaluation.dataset 不存在 → import 失败。
- 再写实现（Green）：load_dataset + Sample，让测试通过。

验收：
- 数据集 ≥ 20 条，四维度（security/quality/performance/structure）全覆盖。
- 每条样本含 id / language / category / code / expected_findings。
"""
from pathlib import Path

from backend.services.evaluation.dataset import Sample, load_dataset

_DATASET = Path(__file__).parent / "eval_samples" / "dataset.json"


def test_load_dataset_returns_list():
    samples = load_dataset(_DATASET)
    assert isinstance(samples, list)
    assert len(samples) >= 20


def test_dataset_covers_four_dimensions():
    samples = load_dataset(_DATASET)
    cats = {s.category for s in samples}
    assert {"security", "quality", "performance", "structure"}.issubset(cats)


def test_dataset_sample_shape():
    samples = load_dataset(_DATASET)
    assert samples  # 非空
    for s in samples:
        assert isinstance(s, Sample)
        assert s.id and s.language and s.code
        assert isinstance(s.expected_findings, list)
        for f in s.expected_findings:
            assert f.severity in {"high", "medium", "low", "info"}
            assert f.category in {"security", "quality", "performance", "structure"}
            assert f.description
