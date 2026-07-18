"""成本控制：Token 计量 + 成本估算（W3: Task 11.3）。

为什么（R0 知识点：成本控制）：
Agent 系统每次审查 = decompose(1) + 4 Worker + judge(1) ≈ 6 次 LLM 调用。
不计量就不知道「一次审查花多少 token、多少钱」——无法做成本优化、无法给面试官讲量化数据。
MCP Gateway（选型 2）的论点是「统一入口可观测」，这里把可观测落到 token 级。

设计：
- TokenMeter：累加每次 completion 的 usage（prompt/completion/total tokens + call_count）。
- MeteredClient：包装 AsyncOpenAI 风格 client，拦截 `.chat.completions.create` 记录 usage，
  其余属性/方法代理到真实 client（不破坏 graph 行为）。
- estimate_cost：按单价（¥/1k tokens）估算成本。单价以官方为准，此处给参考默认值。
"""
from dataclasses import dataclass, field


@dataclass
class TokenMeter:
    """累加 LLM 调用的 token 用量。"""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    call_count: int = 0

    def add(self, usage) -> None:
        """从 OpenAI 风格 usage 对象累加（容忍缺字段）。"""
        if usage is None:
            return
        self.prompt_tokens += getattr(usage, "prompt_tokens", 0) or 0
        self.completion_tokens += getattr(usage, "completion_tokens", 0) or 0
        self.total_tokens += getattr(usage, "total_tokens", 0) or 0
        self.call_count += 1

    def to_dict(self) -> dict:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "call_count": self.call_count,
        }


class MeteredClient:
    """包装 LLM client，记录每次 completion 的 token 用量。

    只拦截 `.chat.completions.create` 这一个调用路径（graph / judge 都走它），
    其余属性/方法（如 .models、.embeddings）原样代理真实 client。
    """

    def __init__(self, real_client, meter: TokenMeter):
        self._real = real_client
        self._meter = meter

    @property
    def chat(self):
        return _MeteredChat(self._real.chat, self._meter)

    def __getattr__(self, name):
        # 未显式处理的属性交给真实 client（如 models / embeddings / base_url）
        return getattr(self._real, name)


class _MeteredChat:
    def __init__(self, real_chat, meter: TokenMeter):
        self._real = real_chat
        self._meter = meter

    @property
    def completions(self):
        return _MeteredCompletions(self._real.completions, self._meter)

    def __getattr__(self, name):
        return getattr(self._real, name)


class _MeteredCompletions:
    def __init__(self, real_completions, meter: TokenMeter):
        self._real = real_completions
        self._meter = meter

    @property
    def create(self):
        meter = self._meter
        real_create = self._real.create

        async def _metered_create(*args, **kwargs):
            resp = await real_create(*args, **kwargs)
            usage = getattr(resp, "usage", None)
            if usage is not None:
                meter.add(usage)
            return resp

        return _metered_create

    def __getattr__(self, name):
        return getattr(self._real, name)


# 参考单价（¥ / 1k tokens）。以官方文档为准，此处仅为演示与可复现的成本估算。
DEFAULT_PRICES = {
    "mimo-v2.5": {"prompt": 0.0, "completion": 0.0},  # 免费模型，成本 0
}


def estimate_cost(meter: TokenMeter, price_per_1k_prompt: float = 0.0, price_per_1k_completion: float = 0.0) -> float:
    """估算成本（¥）= prompt_tokens/1000 * 单价 + completion_tokens/1000 * 单价。"""
    cost = (meter.prompt_tokens / 1000.0) * price_per_1k_prompt
    cost += (meter.completion_tokens / 1000.0) * price_per_1k_completion
    return round(cost, 6)
