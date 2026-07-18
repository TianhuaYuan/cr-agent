"""dev server 启动器：mock fastmcp 后再启动 uvicorn。

沙箱环境装不了 fastmcp，用模块级 mock 绕过。
生产环境不需要这个脚本，直接 `uvicorn backend.main:app`。
"""
import sys
from types import SimpleNamespace

if "fastmcp" not in sys.modules:
    class _FakeFastMCP:
        def __init__(self, name="fake"):
            self.name = name
            self._tools = {}
            self._resources = {}

        def tool(self):
            def decorator(fn):
                self._tools[fn.__name__] = fn
                return fn
            return decorator

        def resource(self, uri):
            def decorator(fn):
                self._resources[uri] = fn
                return fn
            return decorator

        def http_app(self, **kwargs):
            from starlette.applications import Starlette
            from starlette.responses import JSONResponse
            from starlette.routing import Route

            async def _sse(request):
                return JSONResponse({"fake": True})

            return Starlette(routes=[Route("/sse", _sse)])

    _fake = SimpleNamespace(FastMCP=_FakeFastMCP)
    sys.modules["fastmcp"] = _fake
    sys.modules["fastmcp.server"] = _fake
    sys.modules["fastmcp.tools"] = _fake

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8765, reload=False)
