"""ReviewTask 相关 Pydantic schemas（Supervisor 拆解指令 / Worker 产出结果）。

- ``TaskSchema``：Supervisor 把一个 Review 拆成 4 个子任务，每个子任务的「定义/指令」就是它。
- ``TaskResult``：Worker 干完活回传给 Supervisor 的「结果」（发现列表 + 可能的报错）。
"""
from pydantic import BaseModel, Field


class TaskSchema(BaseModel):
    """Supervisor 拆解出的子任务定义（喂给对应 Worker 的指令）。

    role 决定派给哪个 Worker（quality/security/performance/structure）；
    description 是给该 Worker 的具体审查视角说明；priority 用于聚合排序。
    """

    role: str
    description: str
    priority: int = Field(default=2, ge=1, le=5)


class TaskResult(BaseModel):
    """Worker 执行后回传的结果。

    findings 是结构化审查发现列表（每个元素含 severity/line/description 等）；
    error 非空表示这个 Worker 跑挂了（Partial Failure，不影响其他 Worker）；
    status 标记该子任务本身的成功/失败。
    """

    role: str
    findings: list = Field(default_factory=list)
    error: str | None = None
    status: str = "completed"
