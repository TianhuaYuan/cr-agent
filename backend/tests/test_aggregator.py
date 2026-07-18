"""Phase 4 Aggregator + Report 测试（TDD RED → GREEN）。

覆盖：
- aggregate_findings: 去重（同行+同描述 → 合并，来源追加）、排序（severity 降序）、空输入
- generate_report: Markdown 结构（标题/摘要/分维度表格/异常区）
"""
import pytest

from backend.services.aggregator.merge import aggregate_findings
from backend.services.aggregator.report import generate_report


# ── aggregate_findings ──────────────────────────────────────

class TestAggregate:
    def test_empty_input(self):
        """空列表 → 空列表。"""
        assert aggregate_findings([]) == []

    def test_sort_by_severity(self):
        """severity 降序：high > medium > low > info。"""
        findings = [
            {"severity": "info", "line": 1, "description": "a", "worker": "quality"},
            {"severity": "high", "line": 2, "description": "b", "worker": "security"},
            {"severity": "low", "line": 3, "description": "c", "worker": "performance"},
            {"severity": "medium", "line": 4, "description": "d", "worker": "structure"},
        ]
        result = aggregate_findings(findings)
        severities = [f["severity"] for f in result]
        assert severities == ["high", "medium", "low", "info"]

    def test_dedup_same_line_same_description(self):
        """两个 Worker 在同一行发现同一个问题 → 合并为一条，来源追加。"""
        findings = [
            {"severity": "high", "line": 10, "description": "SQL 注入",
             "suggestion": "参数化查询", "code_snippet": "cursor.execute(sql)",
             "worker": "security"},
            {"severity": "medium", "line": 10, "description": "SQL 注入",
             "suggestion": "用 ORM", "code_snippet": "cursor.execute(sql)",
             "worker": "quality"},
        ]
        result = aggregate_findings(findings)
        assert len(result) == 1
        merged = result[0]
        # 合并后取更高 severity
        assert merged["severity"] == "high"
        # 来源列表包含两个 worker
        assert set(merged["sources"]) == {"security", "quality"}

    def test_dedup_different_line_kept(self):
        """不同行号的同类问题 → 不合并，各自保留。"""
        findings = [
            {"severity": "high", "line": 10, "description": "SQL 注入", "worker": "security"},
            {"severity": "high", "line": 20, "description": "SQL 注入", "worker": "security"},
        ]
        result = aggregate_findings(findings)
        assert len(result) == 2

    def test_dedup_case_insensitive_description(self):
        """描述大小写不同但实质相同 → 合并。"""
        findings = [
            {"severity": "medium", "line": 5, "description": "Function too long",
             "worker": "quality"},
            {"severity": "medium", "line": 5, "description": "function too long",
             "worker": "structure"},
        ]
        result = aggregate_findings(findings)
        assert len(result) == 1

    def test_mixed_line_types_does_not_crash(self):
        """line 字段可能是 int 也可能是 str（如 "N/A"，structure Worker 常给字符串行号）→ 排序不应 TypeError 崩溃。

        真实场景：4 个 Worker 并行产出，structure 类问题常无精确行号（line="N/A"），
        与 security/quality 的 int 行号混排会触发 Python 3 int/str 不可比较 → 整次审查失败。
        关键：必须有两个**同 severity** 的 finding 拥有不同类型 line，sort 才会比较第二元触发崩溃。
        """
        findings = [
            {"severity": "high", "line": 10, "description": "硬编码密钥", "worker": "security"},
            {"severity": "high", "line": "N/A", "description": "上帝函数", "worker": "structure"},
            {"severity": "low", "line": 3, "description": "嵌套循环", "worker": "performance"},
        ]
        # 不应抛 TypeError；返回 3 条且 high 两条在前（按 severity 排序）
        result = aggregate_findings(findings)
        assert len(result) == 3
        severities = [f["severity"] for f in result]
        assert severities == ["high", "high", "low"]


# ── generate_report ─────────────────────────────────────────

class TestReport:
    def test_report_has_title_and_summary(self):
        """报告包含标题和摘要区（语言/问题总数/各严重度数量）。"""
        findings = aggregate_findings([
            {"severity": "high", "line": 1, "description": "d1", "suggestion": "s1",
             "code_snippet": "", "worker": "security"},
            {"severity": "low", "line": 2, "description": "d2", "suggestion": "s2",
             "code_snippet": "", "worker": "quality"},
        ])
        report = generate_report(findings, language="python", errors=[])
        assert "# " in report  # 有标题
        assert "python" in report
        assert "2" in report  # 总问题数

    def test_report_grouped_by_worker(self):
        """报告按 Worker 维度分组（quality/security/performance/structure 区块）。"""
        findings = aggregate_findings([
            {"severity": "high", "line": 1, "description": "d1", "suggestion": "s",
             "code_snippet": "", "worker": "security"},
            {"severity": "low", "line": 2, "description": "d2", "suggestion": "s",
             "code_snippet": "", "worker": "quality"},
        ])
        report = generate_report(findings, language="python", errors=[])
        assert "security" in report.lower() or "安全" in report
        assert "quality" in report.lower() or "质量" in report

    def test_report_with_errors_section(self):
        """有 errors → 报告末尾有异常/警告区。"""
        findings = []
        errors = ["SecurityWorker 超时", "PerformanceWorker 异常"]
        report = generate_report(findings, language="python", errors=errors)
        assert "超时" in report or "异常" in report or "警告" in report or "error" in report.lower()

    def test_report_empty_findings(self):
        """无发现 → 报告标注"未发现问题"或类似。"""
        report = generate_report([], language="python", errors=[])
        assert "0" in report or "未发现" in report or "无问题" in report or "no" in report.lower()

    def test_report_dimension_icons_distinct(self):
        """每个 Worker 维度区块应有各自专属图标，而非全部挤同一个（report.py 曾用 severity 字典按 role 查，4 维度全显示 📋）。

        预期映射：security=🔒 / quality=✨ / performance=⚡ / structure=🏗️。
        """
        findings = aggregate_findings([
            {"severity": "high", "line": 1, "description": "d1", "suggestion": "s",
             "code_snippet": "", "worker": "security"},
            {"severity": "medium", "line": 2, "description": "d2", "suggestion": "s",
             "code_snippet": "", "worker": "quality"},
            {"severity": "low", "line": 3, "description": "d3", "suggestion": "s",
             "code_snippet": "", "worker": "performance"},
            {"severity": "info", "line": 4, "description": "d4", "suggestion": "s",
             "code_snippet": "", "worker": "structure"},
        ])
        report = generate_report(findings, language="python", errors=[])
        for icon in ("🔒", "✨", "⚡", "🏗️"):
            assert icon in report, f"维度图标 {icon} 缺失（4 维度应各有专属图标）"
