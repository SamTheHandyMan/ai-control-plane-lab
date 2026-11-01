"""Step 2.1 - a minimal MCP CLIENT, no LLM involved.

Launches catalog_server.py as a subprocess over stdio, performs the MCP handshake,
asks for the tool list (what a model would be shown) and calls the tool once.
"""
import asyncio, json, sys
from mcp.client import Client
from mcp.client.stdio import StdioServerParameters

async def main():
    server = StdioServerParameters(command=sys.executable, args=["catalog_server.py"])
    async with Client(server) as client:
        print("server      :", client.server_info.name if client.server_info else "?")
        tools = await client.list_tools()
        for t in tools.tools:
            print("tool        :", t.name)
            print("description :", t.description.splitlines()[0])
            print("inputSchema :", json.dumps(t.input_schema))
        result = await client.call_tool("lookup_product", {"name": "consent"})
        print("call result :", result.structured_content or result.content[0].text)

asyncio.run(main())
