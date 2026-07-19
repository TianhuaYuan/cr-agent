"""公共工具函数（抽取重复逻辑）。

- extract_json_array: 从 LLM 文本提取 JSON 数组（decompose.py / workers/base.py 共用）
- fetch_pr_code: 从 PR URL 获取代码（reviews.py / webhooks.py 共用）
"""
import json
import re
from typing import Tuple

from backend.integrations import github as github_pkg


def extract_json_array(text: str) -> list:
    """从 LLM 文本提取 JSON 数组。

    LLM 常把 JSON 包在 ```json ... ``` 或夹杂解释文字里，不能直接 json.loads 整个文本。
    先剥掉 markdown 代码围栏（```json / ```），然后用正则抓第一个 '[' 到最后一个 ']'。
    若找不到数组，尝试抓单个对象 {…} 当单元素数组。
    若都找不到，匹配「无问题」关键词 → 返回空数组。
    全部失败抛 ValueError。
    """
    # 先剥掉 markdown 代码围栏 ```json ... ```
    text = re.sub(r"```(?:json)?\s*\n?", "", text)

    # 尝试 JSON 数组
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass

    # 尝试单个 JSON 对象 → 当单元素数组
    obj_match = re.search(r"\{.*\}", text, re.DOTALL)
    if obj_match:
        try:
            obj = json.loads(obj_match.group(0))
            if isinstance(obj, dict):
                return [obj]
        except json.JSONDecodeError:
            pass

    # 尝试匹配「无问题」关键词
    no_issue = re.search(
        r"没[有找到发现]|未[发现找到]|no\s*(issue|problem|finding)s?|nothing\s*(to\s*)?report|clean|all\s*good",
        text, re.IGNORECASE,
    )
    if no_issue:
        return []

    raise ValueError("响应中找不到 JSON 数组")


async def fetch_pr_code(pr_url: str) -> Tuple[str, str]:
    """从 GitHub PR URL 获取代码和语言。

    返回 (code, language) 元组。失败抛 ValueError 或 RuntimeError。
    """
    gh = github_pkg.GitHubClient()
    owner, repo, number = gh.parse_pr_url(pr_url)
    patch = await gh.get_pr_patch(owner, repo, number)
    code = gh.parse_patch_to_code(patch)
    if not code.strip():
        raise ValueError("PR 没有可审查的代码变更")
    language = gh.detect_language(patch)
    return code, language
