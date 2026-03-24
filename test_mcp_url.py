import asyncio
from fastmcp.client import Client
import traceback

async def main():
    config = {
        "mcpServers": {
            "notion": {
                "transport": "sse",
                "url": "https://mcp.notion.com/mcp",
                "headers": {"Authorization": "Bearer fake_token"}
            }
        }
    }
    try:
        client = Client(config)
        async with client:
            tools = await client.session.list_tools()
            print("SUCCESS! Tools:", tools)
    except Exception as e:
        print("SSE Error:", type(e).__name__, str(e))
        traceback.print_exc()

asyncio.run(main())
