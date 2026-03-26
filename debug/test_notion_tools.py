import asyncio
import os
import traceback

from fastmcp.client import Client


async def main():
    config = {
        "mcpServers": {
            "notion": {
                "command": "npx",
                "args": ["-y", "@debuggingmax/mcp-server-notion"],
                "env": {"NOTION_API_TOKEN": "fake_token", "PATH": os.environ.get("PATH", "")}
            }
        }
    }
    try:
        client = Client(config)
        async with client:
            tools = await client.session.list_tools()
            print([t.name for t in tools.tools])
    except Exception:
        traceback.print_exc()

asyncio.run(main())
