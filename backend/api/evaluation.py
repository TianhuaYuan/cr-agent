"""评测相关路由（Task 3: C 功能后端）。

GET /api/v1/evaluation/summary → 评测总览（total / composite_avg / prf_avg / by_category / per_sample）
  - 首次请求加载 dataset + 生成模拟评测结果 + 调用 eval.summarize 聚合
  - 内存缓存，后续 < 50ms
  - ?force=1 强制重新计算

说明（为什么是模拟数据）：
  真实评测需要调用 LLM 跑 graph + judge，耗时长且花钱。
  C 功能的核心目标是"评测面板 UI"，数据是演示用的。
  这里用确定性算法生成模拟评测结果，既能展示 eval 模块的聚合能力，
  又能秒级返回。后续接入真实评测结果时，替换 _build_mock_results 即可。
"""
import json
import logging
import time

from fastapi import APIRouter, Depends, Query

from backend.api.deps import require_auth
from backend.services.evaluation.eval import summarize
from backend.services.evaluation.metrics import compute_prf

logger = logging.getLogger(__name__)

DEFAULT_DATASET = "backend/tests/eval_samples/dataset.json"

_cache: dict = {"data": None, "loaded_at": 0.0}

router = APIRouter(
    prefix="/evaluation",
    tags=["evaluation"],
    dependencies=[Depends(require_auth)],
)


def _load_dataset(path: str) -> list[dict]:
    """加载 dataset.json。"""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _build_mock_results(samples: list[dict]) -> list[dict]:
    """根据样本生成模拟评测结果。

    用确定性伪随机（基于 sample.id 哈希）生成 judgment + prf，
    保证同一数据集结果一致，方便 UI 展示和测试。
    """
    results = []
    for i, s in enumerate(samples):
        seed = sum(ord(c) for c in s["id"]) + i
        completeness = 0.6 + 0.35 * ((seed * 7) % 100) / 100.0
        accuracy = 0.65 + 0.3 * ((seed * 13) % 100) / 100.0
        source_trace = 0.7 + 0.25 * ((seed * 17) % 100) / 100.0
        composite = round(0.4 * completeness + 0.4 * accuracy + 0.2 * source_trace, 4)

        expected = s.get("expected_findings", [])
        actual_count = max(0, len(expected) + ((seed * 3) % 5) - 2)
        actual = expected[:actual_count] if actual_count <= len(expected) else expected + [
            {"severity": "low", "category": s.get("category", "quality"),
             "description": f"额外发现 {j}", "line": 10 + j}
            for j in range(actual_count - len(expected))
        ]
        prf = compute_prf(expected, actual)

        results.append({
            "id": s["id"],
            "category": s["category"],
            "language": s.get("language", "python"),
            "judgment": {
                "completeness": round(completeness, 4),
                "accuracy": round(accuracy, 4),
                "source_traceability": round(source_trace, 4),
                "composite": composite,
                "rationale": "mock data for demo",
            },
            "prf": prf,
        })
    return results


def _compute_summary(dataset_path: str) -> dict:
    """加载数据集 + 生成结果 + 聚合。"""
    samples = _load_dataset(dataset_path)
    results = _build_mock_results(samples)
    summary = summarize(results)
    return summary


@router.get("/summary")
async def get_evaluation_summary(force: bool = Query(False, description="Force refresh cache")):
    """返回评测总览数据。"""
    global _cache

    if _cache["data"] is not None and not force:
        data = dict(_cache["data"])
        data["from_cache"] = True
        return data

    data = _compute_summary(DEFAULT_DATASET)
    _cache["data"] = data
    _cache["loaded_at"] = time.time()
    data["from_cache"] = False
    return data
