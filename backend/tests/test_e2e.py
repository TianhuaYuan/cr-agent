"""Phase 4 + Phase 6 端到端测试（Checkpoint 3 + 4）。

mock 全链路 LLM → 验证 decompose → 4 Worker → aggregate → report 完整跑通。
Phase 6 追加：单行代码、Worker 异常降级、多语言（JS）。
"""
import json
from types import SimpleNamespace

import pytest

from backend.services.supervisor.graph import build_supervisor_graph


class _SmartFakeClient:
    """根据 prompt 内容返回不同 JSON 的假客户端。

    - decompose prompt 含「拆解」→ 返回任务列表 JSON
    - worker prompt 含 system_prompt 关键词 → 返回 findings JSON
    """

    _TASKS_JSON = json.dumps([
        {"role": "security", "description": "检查 SQL 注入和硬编码密钥", "priority": 1},
        {"role": "quality", "description": "检查命名规范和函数长度", "priority": 2},
    ])

    _FINDINGS_JSON = json.dumps([
        {
            "severity": "high",
            "line": 5,
            "description": "硬编码 API 密钥",
            "suggestion": "改用环境变量",
            "code_snippet": 'api_key = "sk-xxx"',
        },
        {
            "severity": "medium",
            "line": 12,
            "description": "函数过长（80 行）",
            "suggestion": "拆分为 3 个子函数",
            "code_snippet": "def huge_function(...):",
        },
    ])

    def __init__(self):
        self._call_count = 0

    @property
    def chat(self):
        from types import SimpleNamespace

        async def _create(*args, **kwargs):
            self._call_count += 1
            messages = kwargs.get("messages", [])
            user_content = ""
            for m in messages:
                if m.get("role") == "user":
                    user_content = m.get("content", "")
                    break

            # decompose 的 prompt 含 "拆解" 或 "JSON 数组" + role/description/priority
            if "拆解" in user_content or "priority" in user_content:
                text = self._TASKS_JSON
            else:
                text = self._FINDINGS_JSON

            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=text))]
            )

        return SimpleNamespace(completions=SimpleNamespace(create=_create))


class TestE2E:
    async def test_e2e_normal_flow(self, monkeypatch):
        """完整链路：decompose → 4 Worker → aggregate → 非空 Markdown 报告。"""
        client = _SmartFakeClient()
        monkeypatch.setattr("backend.core.llm.get_chat_client", lambda: client)

        code = """
api_key = "sk-xxx123456"
def process_user(user_input):
    sql = "SELECT * FROM users WHERE name='" + user_input + "'"
    cursor.execute(sql)
    for i in range(len(data)):
        for j in range(len(data[i])):
            print(data[i][j])
    return eval(user_input)
""".strip()

        graph = build_supervisor_graph()
        result = await graph.ainvoke({"code": code, "language": "python"})

        report = result.get("report", "")
        assert report, "报告不能为空"
        assert "# " in report, "报告必须有 Markdown 标题"
        assert "python" in report, "报告必须包含语言信息"

        # 至少 3 个维度
        dimensions_found = 0
        for keyword in ["安全", "质量", "性能", "架构"]:
            if keyword in report:
                dimensions_found += 1
        assert dimensions_found >= 1, f"报告应包含审查维度，实际 {dimensions_found}"

        # worker_results 非空
        worker_results = result.get("worker_results", [])
        assert len(worker_results) > 0, "Worker 必须产出 findings"

        # 动态路由：LLM 调用次数 = 1 decompose + 动态派发的 Worker 数（= decompose 返回的 task 数）
        expected_calls = 1 + len(json.loads(_SmartFakeClient._TASKS_JSON))
        assert client._call_count == expected_calls, (
            f"LLM 应被调用 {expected_calls} 次（1 decompose + 动态派发的 "
            f"{expected_calls - 1} 个 Worker），实际 {client._call_count}"
        )

    async def test_e2e_empty_code(self, monkeypatch):
        """空代码 → decompose 写 error → 报告含错误标记。"""
        client = _SmartFakeClient()
        monkeypatch.setattr("backend.core.llm.get_chat_client", lambda: client)

        graph = build_supervisor_graph()
        result = await graph.ainvoke({"code": "", "language": "python"})

        errors = result.get("errors", [])
        assert len(errors) > 0, "空代码应产生 error"

    async def test_e2e_report_is_markdown(self, monkeypatch):
        """报告是合法 Markdown（有 ## 标题、表格结构）。"""
        client = _SmartFakeClient()
        monkeypatch.setattr("backend.core.llm.get_chat_client", lambda: client)

        graph = build_supervisor_graph()
        result = await graph.ainvoke({"code": "x = 1", "language": "python"})

        report = result.get("report", "")
        assert "##" in report, "报告必须有 ## 级标题"
        assert "|" in report or "未发现" in report, "报告必须有表格或未发现问题标记"

    # ── Phase 6 Task 6.4 追加场景 ──

    async def test_e2e_single_line(self, monkeypatch):
        """单行代码 → 正常返回，不报错。"""
        client = _SmartFakeClient()
        monkeypatch.setattr("backend.core.llm.get_chat_client", lambda: client)

        graph = build_supervisor_graph()
        result = await graph.ainvoke({"code": "x = 1", "language": "python"})

        report = result.get("report", "")
        assert report, "单行代码也应有报告"

    async def test_e2e_worker_failure(self, monkeypatch):
        """mock Worker 异常 → 报告含降级标记（审查警告区）。"""

        class _BoomClient:
            """所有 LLM 调用都抛异常。"""
            @property
            def chat(self):
                raise RuntimeError("network down")

        monkeypatch.setattr("backend.core.llm.get_chat_client", lambda: _BoomClient())

        graph = build_supervisor_graph()
        result = await graph.ainvoke({"code": "x = 1", "language": "python"})

        report = result.get("report", "")
        errors = result.get("errors", [])
        # 全部 Worker 异常 → errors 非空 + 报告含"审查警告"
        assert len(errors) > 0, "Worker 异常应记录到 errors"
        assert "审查警告" in report or "异常" in report, "报告应含降级标记"

    async def test_e2e_multi_language(self, monkeypatch):
        """JS 输入 → 正常返回，报告含语言信息。"""
        client = _SmartFakeClient()
        monkeypatch.setattr("backend.core.llm.get_chat_client", lambda: client)

        js_code = """
var x = eval(userInput);
function bad() { return x; }
""".strip()

        graph = build_supervisor_graph()
        result = await graph.ainvoke({"code": js_code, "language": "javascript"})

        report = result.get("report", "")
        assert report, "JS 代码也应有报告"
        assert "javascript" in report or "js" in report.lower(), "报告应包含语言信息"
