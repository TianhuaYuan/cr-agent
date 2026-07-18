"""P2：LLM 超时单一来源（W3 代码审查 P2 项）。

验证：客户端与 Worker 的超时都来自 config.LLM_TIMEOUT，
而非散落在两个文件里的魔法常量（60 / 120）。
"""
from backend.core import config
from backend.core.config import settings
from backend.core import llm as llm_mod
from backend.services.workers.quality import QualityWorker


def test_client_timeout_comes_from_config(monkeypatch):
    """LLM 客户端超时必须是单一来源（config.LLM_TIMEOUT）。"""
    monkeypatch.setattr(settings, "LLM_TIMEOUT", 30)
    llm_mod.reset_chat_client()
    try:
        client = llm_mod.get_chat_client()
        assert client.timeout == 30
    finally:
        llm_mod.reset_chat_client()


def test_worker_default_timeout_comes_from_config():
    """Worker 默认超时也应读 config.LLM_TIMEOUT，与客户端同源。"""
    assert QualityWorker().timeout == settings.LLM_TIMEOUT
    # 顺带确认 config 默认值是 120（与历史行为一致，非散落的 60）
    assert config.Settings().LLM_TIMEOUT == 120.0
