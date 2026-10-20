"""Small local MCP example. Uses only the already-installed MCP SDK."""

from mcp.server.fastmcp import FastMCP

server = FastMCP("Local text review")


@server.tool()
def text_statistics(text: str) -> str:
    """Return character and word counts for the supplied text."""
    return f"Characters: {len(text)}; words: {len(text.split())}"


if __name__ == "__main__":
    server.run(transport="stdio")
