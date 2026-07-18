"""LLM Chat 客户端单例（从 1 号项目 rag/clients.py 抽出的极简版）。

只保留 Chat 客户端：Worker 与 Supervisor 复用它调 LLM。
设计要点：单例 + 依赖注入友好——测试时可向调用方传入 fake client，免真实 API key。
"""
import logging

from openai import AsyncOpenAI

from .config import settings

logger = logging.getLogger(__name__)

# 单次 LLM 调用超时（秒）：网络上游必须设超时，防无限挂起
_CHAT_TIMEOUT = 60.0

_chat_client: AsyncOpenAI | None = None


def get_chat_client() -> AsyncOpenAI:
    """返回（惰性创建）Chat 客户端单例。"""
    global _chat_client
    if _chat_client is None:
        _chat_client = AsyncOpenAI(
            api_key=settings.CHAT_API_KEY,
            base_url=settings.CHAT_BASE_URL,
            timeout=_CHAT_TIMEOUT,
        )
    return _chat_client


def reset_chat_client() -> None:
    """清空单例（测试用，便于隔离）。"""
    global _chat_client
    _chat_client = None
