"""指数退避重试（从 1 号项目原样复用，通用无项目依赖）。

用于 Worker 调 LLM / 调外部工具时的 transient 错误重试。
编程错误（TypeError/ValueError/...）立即抛出，不重试。
"""
import asyncio
import logging
from collections.abc import Callable
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

# 不可重试的编程错误（重试也无法修复，应立即暴露）
NON_RETRYABLE = (
    TypeError,
    ValueError,
    AttributeError,
    KeyError,
    IndexError,
    AssertionError,
)


async def with_retry(
    fn: Callable[..., Any],
    *args,
    max_retries: int = 3,
    base_delay: float = 1.0,
    fallback: T | None = None,
    **kwargs: Any,
) -> T:
    """指数退避重试：1s → 2s → 4s。

    - 支持同步 callable 与异步 callable。
    - 编程错误直接抛出，不重试。
    - 耗尽重试后返回 ``fallback``（若提供），否则抛最后错误。
    """
    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            if asyncio.iscoroutinefunction(fn):
                return await fn(*args, **kwargs)
            return fn(*args, **kwargs)  # 同步 callable：直接调用
        except NON_RETRYABLE:
            raise  # 编程错误不重试，直接抛
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                delay = base_delay * (2 ** attempt)
                logger.warning("retry %d/%d after %.1fs: %s", attempt + 1, max_retries, delay, e)
                await asyncio.sleep(delay)
            else:
                logger.error("all %d retries exhausted: %s", max_retries, e)

    if fallback is not None:
        return fallback
    raise last_error  # type: ignore[misc]
