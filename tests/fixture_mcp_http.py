"""Controlled external HTTP MCP endpoint used only by verification tests."""

import os

import uvicorn
from mcp.server.fastmcp import FastMCP
from starlette.responses import JSONResponse

mcp = FastMCP("Controlled verification server", json_response=True, stateless_http=True)


@mcp.tool()
def count_items(items: list[str], label: str = "items") -> str:
    """Count a supplied list. This is a controlled test, not AI inference."""
    return f"{len(items)} {label}"


@mcp.tool()
def server_note() -> str:
    """Read a controlled test note."""
    return "Controlled HTTP MCP server is working."


app = mcp.streamable_http_app()


class Protected:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = dict(scope.get("headers", []))
            bearer = headers.get(b"authorization", b"").decode()
            custom = headers.get(b"x-api-key", b"").decode()
            secret = os.environ["MCP_FIXTURE_KEY"]
            if bearer != "Bearer " + secret and custom != secret:
                await JSONResponse({"error": "Unauthorized"}, status_code=401)(scope, receive, send)
                return
        await self.app(scope, receive, send)


if __name__ == "__main__":
    uvicorn.run(
        Protected(app),
        host="127.0.0.1",
        port=int(os.environ["MCP_FIXTURE_PORT"]),
        log_level="critical",
        access_log=False,
    )
