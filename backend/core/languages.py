"""语言推断映射（扩展名 → 语言）单一来源。

CLI（cli/main.py）与 GitHub 集成（integrations/github.py）都需要把文件扩展名
映射到审查语言，抽到这里避免两处各维护一份相同的 ``_EXT_MAP``
（去重，见 W3 代码审查 P2 项）。
"""
EXT_TO_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".go": "go",
    ".java": "java",
}

# 受支持的语言集合（由映射值推导，单一来源）
VALID_LANGUAGES: frozenset[str] = frozenset(EXT_TO_LANGUAGE.values())
