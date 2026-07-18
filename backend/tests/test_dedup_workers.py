"""P2：Worker 注册表单一来源（W3 代码审查 P2 项）。

验证：Supervisor 图（graph.py）与 MCP Server（mcp/server.py）共用
backend.services.workers.registry.WORKERS，而非各自维护一份相同的 _WORKERS。
"""
def test_registry_is_single_source():
    from backend.services.workers import registry

    assert set(registry.WORKERS.keys()) == {
        "quality",
        "security",
        "performance",
        "structure",
    }
    assert set(registry.SUPPORTED_ROLES) == set(registry.WORKERS.keys())


def test_graph_and_mcp_share_workers():
    from backend.services.workers import registry
    import backend.services.supervisor.graph as graph_mod
    import backend.mcp.server as mcp_mod

    assert graph_mod._WORKERS is registry.WORKERS
    assert mcp_mod._WORKERS is registry.WORKERS
