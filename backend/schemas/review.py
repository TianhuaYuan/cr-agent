"""Review 相关 Pydantic schemas（API 请求/响应）。"""
from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from backend.models.review import Review

_VALID_LANGUAGES = {"python", "javascript", "typescript", "go", "java"}

# ── 多模型 per-request 覆盖：6 个合法 key ──
_VALID_MODEL_OVERRIDE_KEYS = {
    "decompose",
    "worker.quality", "worker.security",
    "worker.performance", "worker.structure",
    "judge",
}


class ReviewRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=50000)
    language: str = Field(..., pattern="^(python|javascript|typescript|go|java)$")
    model_overrides: dict[str, str] | None = None

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def _validate_model_overrides_keys(self):
        """校验 model_overrides 的 key 只允许 6 个预定义角色名，无效 key 抛 ValueError。"""
        if self.model_overrides is not None:
            invalid = set(self.model_overrides) - _VALID_MODEL_OVERRIDE_KEYS
            if invalid:
                raise ValueError(
                    f"model_overrides 包含无效 key: {sorted(invalid)}。"
                    f" 合法 key: {sorted(_VALID_MODEL_OVERRIDE_KEYS)}"
                )
        return self


class PRReviewRequest(BaseModel):
    pr_url: str = Field(..., min_length=10, max_length=500)
    model_overrides: dict[str, str] | None = None

    model_config = {"extra": "forbid"}


class ReviewResponse(BaseModel):
    review_id: str
    status: str
    language: str | None = None
    code_length: int | None = None
    report: str | None = None
    created_at: datetime | None = None
    completed_at: datetime | None = None

    @classmethod
    def from_orm_model(cls, review: Review, review_id: str) -> "ReviewResponse":
        return cls(
            review_id=review_id,
            status=review.status,
            language=review.language,
            code_length=len(review.code_content or ""),
            report=review.report,
            created_at=review.created_at,
            completed_at=review.updated_at if review.status in ("completed", "failed") else None,
        )
