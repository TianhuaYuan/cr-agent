"""GitHub 集成测试（Phase 9: Task 9.1）。

TDD Red → Green：
- 先写测试（Red）：import backend.integrations.github 失败说明模块不存在。
- 再写实现（Green）：让测试通过。

测试策略：注入 fake HTTP client，不依赖真实 GitHub API。
"""

import pytest

from backend.integrations.github import GitHubClient


class _FakeResponse:
    """模拟 httpx.Response（仅覆盖测试用到的字段）。"""

    def __init__(self, text: str, status_code: int = 200):
        self.text = text
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")


class _FakeHTTPClient:
    """模拟 httpx.AsyncClient，注入到 GitHubClient 用于测试。"""

    def __init__(self, body: str, status_code: int = 200):
        self._body = body
        self._status = status_code
        self.last_url = None
        self.last_headers = None

    async def get(self, url: str, headers=None):
        self.last_url = url
        self.last_headers = headers
        return _FakeResponse(self._body, self._status)

    async def aclose(self):
        pass


_SAMPLE_PATCH = """\
From: test <test@example.com>
From: test <test@example.com>
Subject: [PATCH] fix security issue

diff --git a/src/db.py b/src/db.py
index 1111111..2222222 100644
--- a/src/db.py
+++ b/src/db.py
@@ -1,3 +1,4 @@
 def query(sql):
-    cursor.execute(sql)
+    cursor.execute(sql, params)
+    return cursor.fetchall()

diff --git a/src/config.py b/src/config.py
index 3333333..4444444 100644
--- a/src/config.py
+++ b/src/config.py
@@ -1,2 +1,2 @@
 API_KEY = "sk-xxx"
-DEBUG = True
+DEBUG = False
"""


class TestParsePRURL:
    def test_valid_url(self):
        owner, repo, number = GitHubClient.parse_pr_url(
            "https://github.com/octocat/hello-world/pull/42"
        )
        assert owner == "octocat"
        assert repo == "hello-world"
        assert number == 42

    def test_valid_url_with_trailing_slash(self):
        owner, repo, number = GitHubClient.parse_pr_url(
            "https://github.com/octocat/hello-world/pull/42/"
        )
        assert (owner, repo, number) == ("octocat", "hello-world", 42)

    def test_invalid_url_raises(self):
        with pytest.raises(ValueError):
            GitHubClient.parse_pr_url("https://example.com/not/a/pr")


class TestGetPRPatch:
    @pytest.mark.asyncio
    async def test_get_pr_patch_calls_correct_url(self):
        fake = _FakeHTTPClient(_SAMPLE_PATCH)
        client = GitHubClient(token="fake-token", http_client=fake)
        patch = await client.get_pr_patch("octocat", "hello-world", 42)
        assert "diff --git" in patch
        assert fake.last_url == (
            "https://patch-diff.githubusercontent.com/raw/octocat/hello-world/pull/42.patch"
        )
        assert fake.last_headers.get("Authorization") == "Bearer fake-token"

    @pytest.mark.asyncio
    async def test_get_pr_patch_no_token(self):
        fake = _FakeHTTPClient(_SAMPLE_PATCH)
        client = GitHubClient(http_client=fake)
        await client.get_pr_patch("octocat", "hello-world", 1)
        # 没 token 就不带 Authorization 头
        assert "Authorization" not in (fake.last_headers or {})


class TestParsePatchToCode:
    def test_parse_patch_to_code(self):
        client = GitHubClient()
        code = client.parse_patch_to_code(_SAMPLE_PATCH)
        assert "# File: src/db.py" in code
        assert "# File: src/config.py" in code
        assert "cursor.execute(sql, params)" in code
        assert 'API_KEY = "sk-xxx"' in code
        # 删除行（- 开头）不应出现在结果
        assert "-    cursor.execute(sql)" not in code

    def test_parse_patch_to_files(self):
        client = GitHubClient()
        files = client.parse_patch_to_files(_SAMPLE_PATCH)
        assert len(files) == 2
        assert files[0][0] == "src/db.py"
        assert files[1][0] == "src/config.py"
        assert "cursor.execute(sql, params)" in files[0][1]
