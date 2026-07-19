"""Supervisor 工作流的共享状态（数据总线）。

所有节点读写同一个 State 对象：
- ``decompose`` 写 ``tasks``
- 4 个 Worker 各自往 ``worker_results`` 追加结果（``operator.add`` reducer 自动累加）
- ``aggregate`` 读 ``worker_results`` 生成 ``report``

设计要点：``worker_results`` 用 ``Annotated[list, operator.add]``，因为 LangGraph 里
多个 Worker 是并发分支，每个都返回自己的结果片段，框架用 add reducer 把片段拼成完整列表，
节点本身不用关心"别人的结果"。
"""
from typing import Annotated, Optional, TypedDict

import operator


class SupervisorState(TypedDict):
    code: str
    language: str
    review_id: Optional[str]
    tasks: list  # 拆解出的子任务（TaskSchema 的 dict 形态）
    # 多个 Worker 并发写入，operator.add 把各自的结果列表拼起来
    worker_results: Annotated[list, operator.add]
    report: Optional[str]
    iteration_count: int
    max_iterations: int
    # Phase 5: errors 也用 add reducer——多个 Worker 并发各写自己的降级记录，
    # 普通list会被后写者覆盖（LangGraph 节点返回的 dict 做 state 合并时同 key 覆盖），
    # add reducer 保证累加不丢。
    errors: Annotated[list, operator.add]
    # Task 16.2: per-request 多模型覆盖，key=角色名，value=模型名。
    # None 表示不覆盖（走 settings 默认值），由各 LLM 调用点自行处理。
    model_overrides: Optional[dict[str, str]]
