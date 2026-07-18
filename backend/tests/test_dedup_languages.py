"""P2：扩展名→语言映射单一来源（W3 代码审查 P2 项）。

验证：CLI 与 GitHub 集成共用 backend.core.languages.EXT_TO_LANGUAGE，
而非各自维护一份相同的 _EXT_MAP。
"""
def test_languages_module_is_single_source():
    from backend.core import languages

    assert languages.EXT_TO_LANGUAGE == {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".go": "go",
        ".java": "java",
    }
    assert languages.VALID_LANGUAGES == set(languages.EXT_TO_LANGUAGE.values())


def test_github_and_cli_share_ext_map():
    from backend.core import languages
    import backend.integrations.github as gh
    import backend.cli.main as cli

    assert gh.EXT_TO_LANGUAGE is languages.EXT_TO_LANGUAGE
    assert cli.EXT_TO_LANGUAGE is languages.EXT_TO_LANGUAGE
