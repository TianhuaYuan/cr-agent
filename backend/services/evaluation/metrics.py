"""硬指标 precision/recall/F1（W3: Task 11.2）。

为什么（R0 知识点：Agent 评测）：
LLM-as-Judge 是「软指标」——裁判也是 LLM，有方差、有成本。
要证明审查质量，还需要「硬指标」：用 ground truth（expected_findings）和
实际发现（actual findings）比对，算 precision/recall/F1。这是确定性、可复现的。

怎么比：
- 把 expected / actual 的 finding 抽象成 key = (description 前 10 字小写, line)。
- TP = expected 命中 actual（desc 前缀相同 或 line 相同，贪心一对一匹配避免重复计）。
- FN = expected 未命中；FP = actual 未命中 expected。
- precision = TP/(TP+FP)，recall = TP/(TP+FN)，f1 = 2PR/(P+R)。

约定（避免除零 / 空集误判）：
- expected 为空 → precision=recall=f1=1.0（无 ground truth 不扣分）。
- actual 为空且 expected 非空 → recall=0.0，precision=1.0（无假阳性）。
"""


def _key(f: dict) -> tuple:
    desc = (f.get("description") or "").strip().lower()[:10]
    return (desc, f.get("line"))


def compute_prf(expected: list[dict], actual: list[dict]) -> dict:
    """用 ground truth 比对实际发现，返回 precision/recall/f1 + tp/fp/fn。"""
    if not expected:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0, "tp": 0, "fp": 0, "fn": 0}
    if not actual:
        return {
            "precision": 1.0, "recall": 0.0, "f1": 0.0,
            "tp": 0, "fp": 0, "fn": len(expected),
        }

    exp_keys = [_key(e) for e in expected]
    act_keys = [_key(a) for a in actual]
    used = [False] * len(act_keys)

    tp = 0
    for ek in exp_keys:
        for j, ak in enumerate(act_keys):
            if used[j]:
                continue
            desc_match = bool(ek[0]) and bool(ak[0]) and ek[0] == ak[0]
            line_match = ek[1] is not None and ak[1] is not None and ek[1] == ak[1]
            if desc_match or line_match:
                tp += 1
                used[j] = True
                break

    fn = len(expected) - tp
    fp = len(actual) - sum(used)
    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "tp": tp,
        "fp": fp,
        "fn": fn,
    }
