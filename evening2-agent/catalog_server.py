"""Step 2.1 - a tiny MCP server exposing ONE tool over stdio.

MCP (Model Context Protocol) is a JSON-RPC protocol between an AI application
(the *client*/host) and a *server* that offers tools, resources and prompts.
The server knows nothing about which model is calling it; it just answers
"what tools do you have?" (tools/list) and "run this tool" (tools/call).

Run directly:   python catalog_server.py      (waits on stdin for JSON-RPC)
"""
import json
from pathlib import Path
from mcp.server import MCPServer          # mcp>=2: FastMCP was renamed MCPServer

mcp = MCPServer("data-catalog")
CATALOG = json.loads((Path(__file__).parent / "catalog.json").read_text())

@mcp.tool()                               # the function signature + docstring BECOME the tool schema the model sees
def lookup_product(name: str) -> dict:
    """Look up a data product in the enterprise catalog by (partial) name.
    Returns its owner team, SLA and data classification, or an error if not found."""
    q = name.lower().strip()
    for p in CATALOG:
        if q in p["name"]:
            return p
    return {"error": f"no data product matching '{name}'", "known": [p["name"] for p in CATALOG]}

if __name__ == "__main__":
    mcp.run(transport="stdio")            # stdin/stdout carry the protocol; never print() to stdout in a stdio server
