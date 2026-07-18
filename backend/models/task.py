"""ReviewTask —— Supervisor 拆解出的子任务（ORM）。

一个 Review 对应多个 ReviewTask（quality/security/performance/structure 各一个）。
findings 存 Worker 返回的审查发现（JSON 列表）。
"""
from sqlalchemy import ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database import Base


class ReviewTask(Base):
    __tablename__ = "review_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    review_id: Mapped[int] = mapped_column(
        ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # quality/security/performance/structure
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    # Worker 返回的审查发现（JSON 列表）。
    # 用 SQLAlchemy 的 JSON 类型而非 Text：它会在读回时自动反序列化成 Python list，
    # 否则若存成字符串 "[]"，断言 task.findings == [] 会失败（拿到的是字符串不是列表）。
    findings: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
