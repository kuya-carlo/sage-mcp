import json
import logging
from contextvars import ContextVar
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

logger = logging.getLogger("notion")

# Shared context for audit logs during a request lifecycle
audit_logs: ContextVar[list[str] | None] = ContextVar("audit_logs", default=None)


class NotionService:
    def __init__(self, access_token: str):
        self.access_token = access_token
        self.url = "https://mcp.notion.com/mcp"

    async def _call_mcp(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """
        Calls a tool on the official Notion MCP server using the Streamable HTTP transport.
        """
        headers = {"Authorization": f"Bearer {self.access_token}"}

        logs = audit_logs.get()
        if logs is None:
            logs = []
        logs.append(f"🧩 MCP Call (Official): {tool_name}")
        audit_logs.set(logs)

        try:
            async with httpx.AsyncClient(headers=headers) as client:
                async with streamable_http_client(self.url, http_client=client) as streams:
                    read_stream, write_stream, _ = streams
                    async with ClientSession(read_stream, write_stream) as session:
                        await session.initialize()
                        result = await session.call_tool(tool_name, arguments)

                        if result.isError:
                            logger.error(f"MCP Error [{tool_name}]: {result.content}")
                            return {"error": str(result.content)}

                        if result.content and len(result.content) > 0:
                            content = result.content[0]
                            text_content = getattr(content, "text", None)
                            if isinstance(text_content, str | bytes | bytearray):
                                try:
                                    return json.loads(text_content)
                                except json.JSONDecodeError:
                                    return text_content
                        return {}
        except Exception as e:
            logger.error(f"MCP Transport Error: {e}")
            return {"error": str(e)}

    async def create_page(
        self, parent_id: str, title: str, icon_emoji: str = "📚"
    ) -> dict[str, Any]:
        return await self._call_mcp(
            "create_page",
            {
                "parent_id": parent_id,
                "title": title,
                "icon_emoji": icon_emoji,
            },
        )

    async def create_database(
        self, parent_page_id: str, title: str, properties: dict[str, Any]
    ) -> dict[str, Any]:
        return await self._call_mcp(
            "create_database",
            {
                "parent_page_id": parent_page_id,
                "title": title,
                "properties": properties,
            },
        )

    async def create_database_entry(
        self, database_id: str, properties: dict[str, Any]
    ) -> dict[str, Any]:
        return await self._call_mcp(
            "create_database_entry",
            {"database_id": database_id, "properties": properties},
        )

    async def update_page_property(
        self, page_id: str, property_name: str, value: Any
    ) -> dict[str, Any]:
        return await self._call_mcp(
            "update_page_property",
            {
                "page_id": page_id,
                "property_name": property_name,
                "value": value,
            },
        )

    async def create_calendar_entry(
        self, calendar_db_id: str, title: str, date: str, protected: bool
    ) -> dict[str, Any]:
        properties = {
            "Name": {"title": [{"text": {"content": title}}]},
            "Date": {"date": {"start": date}},
            "Protected": {"checkbox": protected},
        }
        return await self.create_database_entry(calendar_db_id, properties)

    async def get_database_entries(
        self, database_id: str, filter_dict: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        return await self._call_mcp(
            "get_database_entries",
            {"database_id": database_id, "filter_dict": filter_dict},
        )

    async def query_tasks_due_this_week(
        self, database_id: str, week_start: str, week_end: str
    ) -> list[dict[str, Any]]:
        filter_dict = {
            "and": [
                {"property": "Due Date", "date": {"on_or_after": week_start}},
                {"property": "Due Date", "date": {"on_or_before": week_end}},
            ]
        }
        return await self.get_database_entries(database_id, filter_dict=filter_dict)

    async def append_block_children(
        self, page_id: str, children: list[dict[str, Any]]
    ) -> dict[str, Any]:
        return await self._call_mcp(
            "append_block_children",
            {"block_id": page_id, "children": children},
        )

    async def get_page(self, page_id: str) -> dict[str, Any]:
        return await self._call_mcp("get_page", {"page_id": page_id})

    async def search_pages(self, query: str) -> list[dict[str, Any]]:
        return await self._call_mcp("search", {"query": query, "object_type": "page"})

    async def search_databases(self, query: str) -> list[dict[str, Any]]:
        return await self._call_mcp("search", {"query": query, "object_type": "database"})
