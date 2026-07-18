"""GitHub 集成（Phase 9: Task 9.1）。

GitHubClient：拉取 PR diff 并解析为可审查代码。

设计选型：
- 用 `.patch` 格式（patch-diff.githubusercontent.com）而非 GitHub REST API。
  原因：.patch 是纯文本 diff，无需 GitHub App / OAuth、不限速、无需 scope 授权，
  适合轻量代码审查场景；REST API 拉 files 需要 token 且分页复杂。
- 依赖注入 http_client：测试可注入 fake client，不触网。同 W1 LLM 注入模式。
- parse_patch_to_code：把多文件 diff 合并成带文件标记的单一 code 字符串，
  交给 supervisor 的 decompose_node 按文件/逻辑再拆成任务。
"""

import re

_PATCH_URL_TMPL = "https://patch-diff.githubusercontent.com/raw/{owner}/{repo}/pull/{number}.patch"
_PR_URL_RE = re.compile(r"https?://github\.com/([^/]+)/([^/]+)/pull/(\d+)")

# 扩展名 → 语言（供 PR patch 语言推断）
_EXT_MAP = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".go": "go",
    ".java": "java",
}


class GitHubClient:
    """GitHub PR 拉取与解析客户端。"""

    def __init__(self, token: str | None = None, http_client=None):
        """
        Args:
            token: GitHub personal access token（可选，仅用于鉴权提限速）。
            http_client: 可注入的 httpx.AsyncClient 兼容对象（测试用）。
                不传则每次请求新建 httpx.AsyncClient。
        """
        self.token = token
        self._http_client = http_client

    @staticmethod
    def parse_pr_url(url: str) -> tuple[str, str, int]:
        """解析 PR URL → (owner, repo, number)。

        支持带/不带尾部斜杠。非法 URL 抛 ValueError。

        例：https://github.com/octocat/hello-world/pull/42 →
            ("octocat", "hello-world", 42)
        """
        m = _PR_URL_RE.match(url)
        if not m:
            raise ValueError(f"无效的 GitHub PR URL: {url}")
        return m.group(1), m.group(2), int(m.group(3))

    async def get_pr_patch(self, owner: str, repo: str, number: int) -> str:
        """拉取 PR 的 .patch 文本（含 unified diff）。"""
        url = _PATCH_URL_TMPL.format(owner=owner, repo=repo, number=number)
        headers = {"Accept": "application/vnd.github.v3.diff"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        if self._http_client is not None:
            resp = await self._http_client.get(url, headers=headers)
            resp.raise_for_status()
            return resp.text

        import httpx

        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            return resp.text

    def parse_patch_to_code(self, patch: str) -> str:
        """把 .patch 解析为带文件标记的单一 code 字符串（供 supervisor 审查）。

        策略：保留 + 开头的新增/修改行，去掉 diff 元数据和 - 删除行，
        每个文件用 `# File: <path>` 标记分段，让 Worker 知道上下文归属。
        """
        lines: list[str] = []
        for line in patch.splitlines():
            if line.startswith("diff --git"):
                m = re.search(r" b/(.+)$", line)
                path = m.group(1) if m else "unknown"
                lines.append(f"# File: {path}")
            elif line.startswith("@@"):
                lines.append(f"# {line}")
            elif line.startswith("+++"):
                continue
            elif line.startswith("---"):
                continue
            elif line.startswith(" "):
                lines.append(line[1:])  # 上下文行：保留，去前导空格
            elif line.startswith("+"):
                lines.append(line[1:])  # 新增行：保留，去前导 +
            # 忽略 - 删除行（不进审查范围）
        return "\n".join(lines)

    def parse_patch_to_files(self, patch: str) -> list[tuple[str, str]]:
        """把 .patch 解析为 [(filename, code), ...]，按文件分组。

        适合「逐文件审查」场景：每个文件独立交给一个 Worker 审查。
        """
        files: list[tuple[str, str]] = []
        current_path: str | None = None
        current_lines: list[str] = []
        for line in patch.splitlines():
            if line.startswith("diff --git"):
                if current_path is not None:
                    files.append((current_path, "\n".join(current_lines)))
                m = re.search(r" b/(.+)$", line)
                current_path = m.group(1) if m else "unknown"
                current_lines = []
            elif line.startswith("@@"):
                continue
            elif line.startswith("+++"):
                continue
            elif line.startswith("---"):
                continue
            elif line.startswith(" "):
                current_lines.append(line[1:])  # 上下文行：保留
            elif line.startswith("+"):
                current_lines.append(line[1:])  # 新增行：保留
        if current_path is not None:
            files.append((current_path, "\n".join(current_lines)))
        return files

    def detect_language(self, patch: str) -> str:
        """从 patch 文件名统计语言，取多数票；无已知扩展名则默认 python。

        供 CLI --pr 与 Webhook 复用（单一来源，避免逻辑重复）。
        """
        from collections import Counter

        counts: dict[str, int] = {}
        for line in patch.splitlines():
            if line.startswith("diff --git"):
                m = re.search(r"\.(\w+)$", line)
                if m:
                    lang = _EXT_MAP.get("." + m.group(1).lower())
                    if lang:
                        counts[lang] = counts.get(lang, 0) + 1
        if not counts:
            return "python"
        return Counter(counts).most_common(1)[0][0]
