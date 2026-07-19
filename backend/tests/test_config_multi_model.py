"""Task 16.1 多模型支持：config 6 个角色 model 字段 + ReviewRequest model_overrides。

TDD RED → GREEN。

覆盖：
- Settings 默认值：6 个角色 model 字段默认 = CHAT_MODEL（向后兼容）
- 环境变量覆盖：CR_AGENT_DECOMPOSE_MODEL 等可独立配置
- ReviewRequest.model_overrides：可选字段，None / dict / 空 dict 均合法
- PRReviewRequest.model_overrides：同步支持
- key 校验：只允许 6 个预定义 key，无效 key 抛 422
"""
import os
import pytest
from fastapi.testclient import TestClient


# ── Settings 6 个角色 model 字段 ───────────────────────────────

def test_settings_has_six_role_model_fields():
    """Settings 必须有 6 个角色 model 字段：DECOMPOSE_MODEL / WORKER_QUALITY_MODEL / WORKER_SECURITY_MODEL / WORKER_PERFORMANCE_MODEL / WORKER_STRUCTURE_MODEL / JUDGE_MODEL。"""
    from backend.core.config import Settings
    fields = Settings.model_fields
    expected = {
        "DECOMPOSE_MODEL",
        "WORKER_QUALITY_MODEL",
        "WORKER_SECURITY_MODEL",
        "WORKER_PERFORMANCE_MODEL",
        "WORKER_STRUCTURE_MODEL",
        "JUDGE_MODEL",
    }
    assert expected.issubset(set(fields.keys())), (
        f"缺少字段: {expected - set(fields.keys())}"
    )


def test_settings_role_models_default_to_chat_model(monkeypatch):
    """6 个角色 model 字段默认值 = CHAT_MODEL（向后兼容，未配置时行为不变）。"""
    monkeypatch.setenv("CR_AGENT_CHAT_MODEL", "gpt-4o-mini")
    # 清空 6 个角色 model 的环境变量（确保走默认值）
    for key in [
        "CR_AGENT_DECOMPOSE_MODEL",
        "CR_AGENT_WORKER_QUALITY_MODEL",
        "CR_AGENT_WORKER_SECURITY_MODEL",
        "CR_AGENT_WORKER_PERFORMANCE_MODEL",
        "CR_AGENT_WORKER_STRUCTURE_MODEL",
        "CR_AGENT_JUDGE_MODEL",
    ]:
        monkeypatch.delenv(key, raising=False)

    from backend.core.config import Settings
    s = Settings()
    assert s.CHAT_MODEL == "gpt-4o-mini"
    assert s.DECOMPOSE_MODEL == "gpt-4o-mini"
    assert s.WORKER_QUALITY_MODEL == "gpt-4o-mini"
    assert s.WORKER_SECURITY_MODEL == "gpt-4o-mini"
    assert s.WORKER_PERFORMANCE_MODEL == "gpt-4o-mini"
    assert s.WORKER_STRUCTURE_MODEL == "gpt-4o-mini"
    assert s.JUDGE_MODEL == "gpt-4o-mini"


def test_settings_role_models_independent_env_override(monkeypatch):
    """每个角色 model 字段可独立通过环境变量覆盖。"""
    monkeypatch.setenv("CR_AGENT_CHAT_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("CR_AGENT_DECOMPOSE_MODEL", "deepseek-chat")
    monkeypatch.setenv("CR_AGENT_WORKER_QUALITY_MODEL", "gpt-4o")
    monkeypatch.setenv("CR_AGENT_WORKER_SECURITY_MODEL", "glm-4.5")
    monkeypatch.setenv("CR_AGENT_WORKER_PERFORMANCE_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("CR_AGENT_WORKER_STRUCTURE_MODEL", "gpt-4o")
    monkeypatch.setenv("CR_AGENT_JUDGE_MODEL", "claude-sonnet-4")

    from backend.core.config import Settings
    s = Settings()
    assert s.DECOMPOSE_MODEL == "deepseek-chat"
    assert s.WORKER_QUALITY_MODEL == "gpt-4o"
    assert s.WORKER_SECURITY_MODEL == "glm-4.5"
    assert s.WORKER_PERFORMANCE_MODEL == "gpt-4o-mini"
    assert s.WORKER_STRUCTURE_MODEL == "gpt-4o"
    assert s.JUDGE_MODEL == "claude-sonnet-4"


# ── ReviewRequest.model_overrides 字段 ──────────────────────────

def test_review_request_has_model_overrides_field():
    """ReviewRequest 必须有 model_overrides 字段。"""
    from backend.schemas.review import ReviewRequest
    fields = ReviewRequest.model_fields
    assert "model_overrides" in fields


def test_review_request_model_overrides_default_none():
    """model_overrides 默认 None（向后兼容，不传时行为不变）。"""
    from backend.schemas.review import ReviewRequest
    req = ReviewRequest(code="x=1", language="python")
    assert req.model_overrides is None


def test_review_request_model_overrides_accepts_dict():
    """model_overrides 接受 dict[str, str] 类型。"""
    from backend.schemas.review import ReviewRequest
    req = ReviewRequest(
        code="x=1",
        language="python",
        model_overrides={"decompose": "deepseek-chat", "judge": "gpt-4o"},
    )
    assert req.model_overrides == {"decompose": "deepseek-chat", "judge": "gpt-4o"}


def test_review_request_model_overrides_accepts_empty_dict():
    """空 dict 也合法（表示不覆盖任何角色）。"""
    from backend.schemas.review import ReviewRequest
    req = ReviewRequest(code="x=1", language="python", model_overrides={})
    assert req.model_overrides == {}


# ── key 校验：无效 key 抛 422 ─────────────────────────────────

VALID_KEYS = {
    "decompose",
    "worker.quality",
    "worker.security",
    "worker.performance",
    "worker.structure",
    "judge",
}


def test_review_request_model_overrides_accepts_all_valid_keys():
    """6 个预定义 key 都合法。"""
    from backend.schemas.review import ReviewRequest
    req = ReviewRequest(
        code="x=1",
        language="python",
        model_overrides={k: "gpt-4o" for k in VALID_KEYS},
    )
    assert len(req.model_overrides) == 6


def test_review_request_model_overrides_rejects_invalid_key():
    """无效 key（如 'unknown' / 'worker' / 'worker.bad'）应触发 422。

    校验方式：用 FastAPI TestClient 实际 POST，验证返回 422 而非 200。
    """
    from backend.main import create_app
    app = create_app()
    client = TestClient(app)

    # 用无效 key
    response = client.post(
        "/api/v1/reviews",
        json={
            "code": "x=1",
            "language": "python",
            "model_overrides": {"unknown_role": "gpt-4o"},
        },
    )
    assert response.status_code == 422, (
        f"无效 key 应触发 422，实际 {response.status_code}: {response.text}"
    )


def test_review_request_model_overrides_rejects_worker_without_subrole():
    """'worker' 不是合法 key（必须是 'worker.quality' 等带子角色）。"""
    from backend.schemas.review import ReviewRequest
    from pydantic import ValidationError

    with pytest.raises((ValidationError, ValueError)):
        ReviewRequest(
            code="x=1",
            language="python",
            model_overrides={"worker": "gpt-4o"},
        )


# ── PRReviewRequest 同步加 model_overrides ────────────────────

def test_pr_review_request_has_model_overrides_field():
    """PRReviewRequest 也必须有 model_overrides 字段（PR 审查同样支持多模型）。"""
    from backend.schemas.review import PRReviewRequest
    fields = PRReviewRequest.model_fields
    assert "model_overrides" in fields


def test_pr_review_request_model_overrides_default_none():
    """PRReviewRequest.model_overrides 默认 None。"""
    from backend.schemas.review import PRReviewRequest
    req = PRReviewRequest(pr_url="https://github.com/owner/repo/pull/1")
    assert req.model_overrides is None


# ── 鉴权态下端点能透传 model_overrides（不回归）──────────────

def test_review_request_model_overrides_does_not_break_existing_request(monkeypatch):
    """不传 model_overrides 时（旧行为）应该正常工作，不回归。"""
    from backend.schemas.review import ReviewRequest
    # 旧 client 不传 model_overrides
    req = ReviewRequest(code="x=1", language="python")
    assert req.code == "x=1"
    assert req.language == "python"
    assert req.model_overrides is None
