import json
from typing import Dict, Any, List, Optional
import os
from fastmcp.client import Client
from contextlib import asynccontextmanager

class NotionService:
    @asynccontextmanager
    async def _mcp_client(self, access_token: str):
        config = {
            "mcpServers": {
                "notion": {
                    "command": "uv",
                    "args": ["run", "fastmcp", "run", "sage/services/notion_mcp.py:notion_mcp"],
                    "env": {"NOTION_API_TOKEN": access_token, "PATH": os.environ.get("PATH", "")}
                }
            }
        }
        client = Client(config)
        async with client:
            yield client
            
    async def _call_mcp(self, access_token: str, action: str, params: dict):
        async with self._mcp_client(access_token) as client:
            result = await client.session.call_tool(action, params)
            if result.content and len(result.content) > 0:
                try:
                    return json.loads(result.content[0].text)
                except Exception as e:
                    print(f"Error parsing MCP output for {action}: {e}")
            return None

    async def create_page(self, access_token: str, parent_id: str, title: str, icon_emoji: str = "📚") -> Dict[str, Any]:
        return await self._call_mcp(access_token, "create_page", {
            "parent_id": parent_id,
            "title": title,
            "icon_emoji": icon_emoji
        })

    async def create_database(self, access_token: str, parent_page_id: str, title: str, properties: Dict[str, Any]) -> Dict[str, Any]:
        return await self._call_mcp(access_token, "create_database", {
            "parent_page_id": parent_page_id,
            "title": title,
            "properties": properties
        })

    async def create_database_entry(self, access_token: str, database_id: str, properties: Dict[str, Any]) -> Dict[str, Any]:
        return await self._call_mcp(access_token, "create_database_entry", {
            "database_id": database_id,
            "properties": properties
        })

    async def update_page_property(self, access_token: str, page_id: str, property_name: str, value: Any) -> Dict[str, Any]:
        return await self._call_mcp(access_token, "update_page_property", {
            "page_id": page_id,
            "property_name": property_name,
            "value": value
        })

    async def create_calendar_entry(self, access_token: str, calendar_db_id: str, title: str, date: str, protected: bool) -> Dict[str, Any]:
        properties = {
            "Name": {"title": [{"text": {"content": title}}]},
            "Date": {"date": {"start": date}},
            "Protected": {"checkbox": protected}
        }
        return await self.create_database_entry(access_token, calendar_db_id, properties)

    async def get_database_entries(self, access_token: str, database_id: str, filter_dict: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        res = await self._call_mcp(access_token, "get_database_entries", {
            "database_id": database_id,
            "filter_dict": filter_dict
        })
        return res if res is not None else []

    async def query_tasks_due_this_week(self, access_token: str, database_id: str, week_start: str, week_end: str) -> List[Dict[str, Any]]:
        filter_dict = {
            "and": [
                {"property": "Due Date", "date": {"on_or_after": week_start}},
                {"property": "Due Date", "date": {"on_or_before": week_end}}
            ]
        }
        return await self.get_database_entries(access_token, database_id, filter_dict=filter_dict)

    async def append_block_children(self, access_token: str, page_id: str, children: List[Dict[str, Any]]) -> Dict[str, Any]:
        await self._call_mcp(access_token, "append_block_children", {
            "block_id": page_id,
            "children": children
        })
        return {"status": "success"}

    async def get_page(self, access_token: str, page_id: str) -> Dict[str, Any]:
        return await self._call_mcp(access_token, "get_page", {
            "page_id": page_id
        })

    async def search_pages(self, access_token: str, query: str) -> List[Dict[str, Any]]:
        res = await self._call_mcp(access_token, "search", {"query": query})
        if isinstance(res, list):
            return res
        elif isinstance(res, dict):
            return res.get("results", [])
        return []

