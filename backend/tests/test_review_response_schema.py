"""P3：ReviewResponse 死字段清理（W3 代码审查 P3 项）。

task_count / findings / errors 从未被 from_orm_model 填充（ORM 模型也不存这些字段），
永远是 None，是误导性的死字段，应移除。
"""
from backend.schemas.review import ReviewResponse


def test_review_response_has_no_dead_fields():
    for dead in ("task_count", "findings", "errors"):
        assert dead not in ReviewResponse.model_fields
