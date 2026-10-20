"""Actual MCP stdio server, exposing only bundled teaching documents."""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("AgentSim teaching documents")
DOCUMENTS = {
    "picnic": "Bring water, fruit, sandwiches, a blanket and a rubbish bag. Check the weather. Ask about food allergies.",
    "teamwork": "A researcher gathers facts. A writer makes a clear draft. A reviewer checks the draft.",
}


@mcp.tool()
def search(query: str) -> str:
    """Search the bundled teaching documents by keyword."""
    words = query.lower().split()
    return (
        "\n".join(
            f"{k}: {v}"
            for k, v in DOCUMENTS.items()
            if any(w in (k + " " + v).lower() for w in words)
        )
        or "No matching documents."
    )


@mcp.tool()
def read(document_id: str) -> str:
    """Read one bundled document: picnic or teamwork."""
    return DOCUMENTS.get(document_id, "Document not found. Available: picnic, teamwork.")


if __name__ == "__main__":
    mcp.run(transport="stdio")
