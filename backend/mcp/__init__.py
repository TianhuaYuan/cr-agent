"""MCP Gateway 模块。

导出 FastMCP 实例，供 main.py 挂载到 FastAPI app 的 /mcp 路径。
"""
from backend.mcp.server import mcp

__all__ = ["mcp"]
