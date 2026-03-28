import json
import logging
from contextvars import ContextVar
from typing import Any

from fastmcp.client import Client

from sage.config import settings

# Shared context for audit logs during a request lifecycle
audit_logs: ContextVar[list[str] | None] = ContextVar("audit_logs", default=None)

logger = logging.getLogger("notion")


class NotionService:
    def __init__(self):
        # We'll use the local SSE endpoint mounted in main.py
        self.url = f"http://127.0.0.1:{settings.port}/notion-native-mcp"

    def _log(self, message: str):
        logs = audit_logs.get()
        if logs is None:
            logs = []
        logs.append(message)
        audit_logs.set(logs)
        logger.info(message)

    async def _call_mcp(self, action: str, params: dict) -> Any:
        """
        Calls a tool on the Notion Native MCP server using the SSE transport.
        This fulfills the 'STREAMABLE HTTP/SSE' requirement.
        """
        self._log(f"🧩 MCP Call (SSE): {action}")

        config = {
            "mcpServers": {
                "notion": {
                    "url": f"{self.url}/sse",
                    "transport": "sse",
                }
            }
        }

        try:
            async with Client(config) as client:
                # FastMCP Client handles the SSE connection and tool calling protocol
                result = await client.session.call_tool(action, params)

                if result.content and len(result.content) > 0:
                    text_content = result.content[0].text
                    try:
                        return json.loads(text_content)
                    except json.JSONDecodeError:
                        return text_content
                return {}
        except Exception as e:
            self._log(f"❌ MCP SSE Error: {e}")
            return {"error": str(e)}

    async def create_page(
        self, access_token: str, parent_id: str, title: str, icon_emoji: str = "📚"
    ) -> dict[str, Any]:
        self._log(f"📝 Creating page: '{title}'")
        return await self._call_mcp(
            "create_page",
            {
                "parent_id": parent_id,
                "title": title,
                "icon_emoji": icon_emoji,
                "access_token": access_token,
            },
        )

    async def create_database(
        self, access_token: str, parent_page_id: str, title: str, properties: dict[str, Any]
    ) -> dict[str, Any]:
        self._log(f"🗄️ Creating database: '{title}'")
        return await self._call_mcp(
            "create_database",
            {
                "parent_page_id": parent_page_id,
                "title": title,
                "properties": properties,
                "access_token": access_token,
            },
        )

    async def create_database_entry(
        self, access_token: str, database_id: str, properties: dict[str, Any]
    ) -> dict[str, Any]:
        self._log(f"➕ Adding entry to database {database_id[:8]}...")
        return await self._call_mcp(
            "create_database_entry",
            {"database_id": database_id, "properties": properties, "access_token": access_token},
        )

    async def update_page_property(
        self, access_token: str, page_id: str, property_name: str, value: Any
    ) -> dict[str, Any]:
        self._log(f"✏️ Updating property '{property_name}' on page {page_id[:8]}...")
        return await self._call_mcp(
            "update_page_property",
            {
                "page_id": page_id,
                "property_name": property_name,
                "value": value,
                "access_token": access_token,
            },
        )

    async def create_calendar_entry(
        self, access_token: str, calendar_db_id: str, title: str, date: str, protected: bool
    ) -> dict[str, Any]:
        properties = {
            "Name": {"title": [{"text": {"content": title}}]},
            "Date": {"date": {"start": date}},
            "Protected": {"checkbox": protected},
        }
        return await self.create_database_entry(access_token, calendar_db_id, properties)

    async def get_database_entries(
        self, access_token: str, database_id: str, filter_dict: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        self._log(f"🔍 Querying database {database_id[:8]}...")
        return await self._call_mcp(
            "get_database_entries",
            {"database_id": database_id, "filter_dict": filter_dict, "access_token": access_token},
        )

    async def query_tasks_due_this_week(
        self, access_token: str, database_id: str, week_start: str, week_end: str
    ) -> list[dict[str, Any]]:
        filter_dict = {
            "and": [
                {"property": "Due Date", "date": {"on_or_after": week_start}},
                {"property": "Due Date", "date": {"on_or_before": week_end}},
            ]
        }
        return await self.get_database_entries(access_token, database_id, filter_dict=filter_dict)

    async def append_block_children(
        self, access_token: str, page_id: str, children: list[dict[str, Any]]
    ) -> dict[str, Any]:
        self._log(f"📦 Appending {len(children)} blocks to page {page_id[:8]}...")
        return await self._call_mcp(
            "append_block_children",
            {"block_id": page_id, "children": children, "access_token": access_token},
        )

    async def get_page(self, access_token: str, page_id: str) -> dict[str, Any]:
        self._log(f"📄 Fetching page {page_id[:8]}...")
        return await self._call_mcp("get_page", {"page_id": page_id, "access_token": access_token})

    async def search_pages(self, access_token: str, query: str) -> list[dict[str, Any]]:
        self._log(f"🔎 Searching for page: '{query}'")
        return await self._call_mcp(
            "search", {"query": query, "object_type": "page", "access_token": access_token}
        )

    async def search_databases(self, access_token: str, query: str) -> list[dict[str, Any]]:
        self._log(f"🔎 Searching for database: '{query}'")
        return await self._call_mcp(
            "search", {"query": query, "object_type": "database", "access_token": access_token}
        )
