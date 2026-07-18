"""评测主流程（Phase 10: Task 10.2，W3: Task 11.1 扩展）。

run_one：单条样本 → supervisor graph 审查 → LLM-as-Judge 评分 → 返回原始 findings。
run_samples / run_all：遍历样本 → 汇总（总体 + 分类聚合）。
summarize / summarize_by_category：聚合计算。
render_report：渲染 Markdown 评测报告。

CLI：
  python -m backend.services.evaluation.eval --limit 5
  python scripts/eval.py --all --report eval_report.md
"""
import argparse
import asyncio
import json
from pathlib import Path
from statistics import mean

from backend.services.aggregator.merge import aggregate_findings
from backend.services.evaluation.dataset import Sample, load_dataset
from backend.services.evaluation.judge import judge_with_llm
from backend.services.evaluation.metrics import compute_prf
from backend.services.supervisor.graph import build_supervisor_graph


async def run_one(sample: Sample, judge_client=None, meter=None) -> dict:
    """单条样本评测：graph 审查 → judge 评分。

    返回 dict 含：id / category / language / judgment / findings（graph 原始 findings）。
    meter 为可选 TokenMeter（W3 Task 11.3 接入），传入则用 MeteredClient 包 graph client。
    """
    graph_client = None
    original_getter = None
    if meter is not None:
        from backend.services.evaluation.cost import MeteredClient
        from backend.core import llm as llm_mod

        original_getter = llm_mod.get_chat_client
        real = original_getter()
        graph_client = MeteredClient(real, meter)
        llm_mod.get_chat_client = lambda: graph_client

    try:
        graph = build_supervisor_graph()
        result = await graph.ainvoke({"code": sample.code, "language": sample.language})
    finally:
        if original_getter is not None:
            from backend.core import llm as llm_mod

            llm_mod.get_chat_client = original_getter  # 还原原始函数，避免污染

    report = result.get("report", "")
    # 用聚合后的去重 findings 作为「实际发现」（与报告一致），PRF 比对更准
    findings = aggregate_findings(result.get("worker_results", []))
    expected = [f.__dict__ for f in sample.expected_findings]
    prf = compute_prf(expected, findings)
    judgment = await judge_with_llm(sample.code, expected, report, client=judge_client)
    return {
        "id": sample.id,
        "category": sample.category,
        "language": sample.language,
        "judgment": judgment.to_dict(),
        "findings": findings,
        "prf": prf,
        "report": report,
    }


async def run_samples(samples: list[Sample], judge_client=None, meter=None, limit: int | None = None) -> list[dict]:
    """遍历样本评测，返回每条结果（单条失败不影响整体）。"""
    if limit:
        samples = samples[:limit]
    results: list[dict] = []
    for s in samples:
        try:
            results.append(await run_one(s, judge_client=judge_client, meter=meter))
        except Exception as e:  # 单条失败不影响整体
            results.append({"id": s.id, "category": s.category, "error": str(e)})
    return results


async def run_all(dataset_path: str | Path, limit: int | None = None, meter=None) -> dict:
    """遍历数据集评测，返回汇总（含每条分数 + 总体 + 分类聚合）。"""
    samples = load_dataset(dataset_path)
    results = await run_samples(samples, limit=limit, meter=meter)
    summary = summarize(results)
    summary["tokens"] = meter.to_dict() if meter is not None else None
    return summary


def summarize(results: list[dict]) -> dict:
    """从每条结果聚合：总体 composite_avg / prf_avg / by_category。"""
    scored = [r for r in results if "judgment" in r]
    composite_avg = mean(r["judgment"]["composite"] for r in scored) if scored else 0.0
    prf_list = [r["prf"] for r in scored if "prf" in r]
    prf_avg = _avg_prf(prf_list) if prf_list else None
    return {
        "total": len(results),
        "composite_avg": round(composite_avg, 4),
        "prf_avg": prf_avg,
        "by_category": summarize_by_category(scored),
        "per_sample": results,
    }


def summarize_by_category(results: list[dict]) -> dict:
    """按 category 聚合：count + 各维度均值 + prf 均值。"""
    groups: dict[str, list[dict]] = {}
    for r in results:
        groups.setdefault(r["category"], []).append(r)

    out: dict[str, dict] = {}
    for cat, rs in groups.items():
        out[cat] = {
            "count": len(rs),
            "composite_avg": round(mean(x["judgment"]["composite"] for x in rs), 4),
            "completeness_avg": round(mean(x["judgment"]["completeness"] for x in rs), 4),
            "accuracy_avg": round(mean(x["judgment"]["accuracy"] for x in rs), 4),
            "source_avg": round(mean(x["judgment"]["source_traceability"] for x in rs), 4),
            "prf": _avg_prf([x["prf"] for x in rs if "prf" in x]),
        }
    return out


def _avg_prf(prf_list: list[dict]) -> dict | None:
    if not prf_list:
        return None
    return {
        "precision": round(mean(x.get("precision", 0.0) for x in prf_list), 4),
        "recall": round(mean(x.get("recall", 0.0) for x in prf_list), 4),
        "f1": round(mean(x.get("f1", 0.0) for x in prf_list), 4),
    }


def render_report(summary: dict) -> str:
    """渲染 Markdown 评测报告。"""
    lines: list[str] = []
    lines.append("# cr-agent 评测报告")
    lines.append("")
    lines.append("## 总览")
    lines.append("")
    lines.append(f"- 样本总数：**{summary['total']}**")
    lines.append(f"- 综合得分 composite_avg：**{summary['composite_avg']}**")
    if summary.get("prf_avg"):
        p = summary["prf_avg"]
        lines.append(f"- 硬指标 PRF：precision={p['precision']} / recall={p['recall']} / f1={p['f1']}")
    if summary.get("tokens"):
        t = summary["tokens"]
        lines.append(
            f"- Token 用量：prompt={t['prompt_tokens']} / completion={t['completion_tokens']} "
            f"/ total={t['total_tokens']} / calls={t['call_count']}"
        )
    lines.append("")

    lines.append("## 分类明细")
    lines.append("")
    lines.append("| 类别 | 样本数 | composite | completeness | accuracy | source | PRF-f1 |")
    lines.append("|------|--------|-----------|--------------|----------|--------|--------|")
    for cat, m in summary["by_category"].items():
        prf_f1 = m["prf"]["f1"] if m.get("prf") else "-"
        lines.append(
            f"| {cat} | {m['count']} | {m['composite_avg']} | {m['completeness_avg']} "
            f"| {m['accuracy_avg']} | {m['source_avg']} | {prf_f1} |"
        )
    lines.append("")

    lines.append("## 每条样本")
    lines.append("")
    for r in summary["per_sample"]:
        if "error" in r:
            lines.append(f"### {r['id']} ❌ 错误：{r['error']}")
            lines.append("")
            continue
        j = r["judgment"]
        prf = r.get("prf")
        prf_str = f" / PRF-f1={prf['f1']}" if prf else ""
        lines.append(
            f"### {r['id']}（{r['category']}）— composite={j['composite']}{prf_str}"
        )
        lines.append("")
        lines.append(f"- completeness={j['completeness']} / accuracy={j['accuracy']} / source={j['source_traceability']}")
        if j.get("rationale"):
            lines.append(f"- 裁判理由：{j['rationale']}")
        lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="cr-agent LLM-as-Judge 评测")
    default_dataset = (
        Path(__file__).resolve().parent.parent.parent
        / "tests"
        / "eval_samples"
        / "dataset.json"
    )
    parser.add_argument("--dataset", default=str(default_dataset))
    parser.add_argument("--limit", type=int, default=None, help="只评测前 N 条")
    parser.add_argument("--out", default="eval_report.json", help="JSON 输出路径")
    parser.add_argument("--report", default=None, help="Markdown 报告输出路径")
    parser.add_argument("--tokens", action="store_true", help="计量 token 用量（graph + judge 全量）")
    args = parser.parse_args()

    meter = None
    if args.tokens:
        from backend.services.evaluation.cost import TokenMeter

        meter = TokenMeter()
    summary = asyncio.run(run_all(args.dataset, args.limit, meter=meter))
    Path(args.out).write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if args.report:
        Path(args.report).write_text(render_report(summary), encoding="utf-8")
    print(f"评测完成：{summary['total']} 条，composite_avg={summary['composite_avg']}")


if __name__ == "__main__":
    main()
