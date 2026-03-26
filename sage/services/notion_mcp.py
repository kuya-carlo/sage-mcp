import httpx
from fastmcp import FastMCP
import os
import sys
from typing import Any, Optional
from dotenv import load_dotenv

load_dotenv()

notion_mcp = FastMCP("Notion Native Python MCP")

BASE_URL = "https://api.notion.com/v1"
VERSION = "2022-06-28"

def _get_headers() -> dict:
    access_token = os.environ.get("NOTION_API_TOKEN")
    if not access_token:
        raise ValueError("NOTION_API_TOKEN is missing in environment variables.")
    return {
        "Authorization": f"Bearer {access_token}",
        "Notion-Version": VERSION,
        "Content-Type": "application/json"
    }

@notion_mcp.tool()
async def append_block_children(block_id: str, children: list) -> dict:
    block_id = block_id.strip()
    url = f"{BASE_URL}/blocks/{block_id}/children"
    payload = {"children": children}
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.patch(url, headers=_get_headers(), json=payload)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            msg = f"Notion API error (append_block_children): {e.response.text}"
            print(msg, file=sys.stderr)
            return {"error": msg, "status": e.response.status_code}

@notion_mcp.tool()
async def search(query: str, object_type: str = "page") -> list:
    url = f"{BASE_URL}/search"
    payload: dict = {
        "filter": {
            "property": "object",
            "value": object_type
        }
    }
    if query:
        payload["query"] = query
        
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(url, headers=_get_headers(), json=payload)
            response.raise_for_status()
            data = response.json()
            return data.get("results", [])
        except httpx.HTTPStatusError as e:
            msg = f"Notion API error (search): {e.response.text}"
            print(msg, file=sys.stderr)
            return {"error": msg, "status": e.response.status_code}

@notion_mcp.tool()
async def create_page(parent_id: str, title: str, icon_emoji: str = "📚") -> dict:
    parent_id = parent_id.strip()
    url = f"{BASE_URL}/pages"
    payload = {
        "parent": {"page_id": parent_id},
        "properties": {"title": [{"type": "text", "text": {"content": title}}]},
        "icon": {"type": "emoji", "emoji": icon_emoji}
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(url, headers=_get_headers(), json=payload)
            response.raise_for_status()
            data = response.json()
            return {"id": data["id"], "url": data.get("url", "")}
        except httpx.HTTPStatusError as e:
            msg = f"Notion API error (create_page): {e.response.text}"
            print(msg, file=sys.stderr)
            return {"error": msg, "status": e.response.status_code}

@notion_mcp.tool()
async def create_database(parent_page_id: str, title: str, properties: dict) -> dict:
    parent_page_id = parent_page_id.strip()
    url = f"{BASE_URL}/databases"
    payload = {
        "parent": {"page_id": parent_page_id},
        "title": [{"type": "text", "text": {"content": title}}],
        "properties": properties
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(url, headers=_get_headers(), json=payload)
            response.raise_for_status()
            data = response.json()
            return {"id": data["id"]}
        except httpx.HTTPStatusError as e:
            msg = f"Notion API error (create_database): {e.response.text}"
            print(msg, file=sys.stderr)
            return {"error": msg, "status": e.response.status_code}


@notion_mcp.tool()
async def create_database_entry(database_id: str, properties: dict) -> dict:
    database_id = database_id.strip()
    url = f"{BASE_URL}/pages"
    payload = {
        "parent": {"database_id": database_id},
        "properties": properties
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(url, headers=_get_headers(), json=payload)
            response.raise_for_status()
            data = response.json()
            return {"id": data["id"]}
        except httpx.HTTPStatusError as e:
            msg = f"Notion API error (create_database_entry): {e.response.text}"
            print(msg, file=sys.stderr)
            return {"error": msg, "status": e.response.status_code}

@notion_mcp.tool()
async def update_page_property(page_id: str, property_name: str, value: dict) -> dict:
    page_id = page_id.strip()
    url = f"{BASE_URL}/pages/{page_id}"
    payload = {"properties": {property_name: value}}
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.patch(url, headers=_get_headers(), json=payload)
            response.raise_for_status()
            data = response.json()
            return {"id": data["id"]}
        except httpx.HTTPStatusError as e:
            msg = f"Notion API error (update_page_property): {e.response.text}"
            print(msg, file=sys.stderr)
            return {"error": msg, "status": e.response.status_code}

@notion_mcp.tool()
async def get_database_entries(database_id: str, filter_dict: dict = None) -> list:
    database_id = database_id.strip()
    url = f"{BASE_URL}/databases/{database_id}/query"
    payload = {}
    if filter_dict:
        payload["filter"] = filter_dict
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(url, headers=_get_headers(), json=payload)
            response.raise_for_status()
            data = response.json()
            return data.get("results", [])
        except httpx.HTTPStatusError as e:
            msg = f"Notion API error (get_database_entries): {e.response.text}"
            print(msg, file=sys.stderr)
            return {"error": msg, "status": e.response.status_code}

@notion_mcp.tool()
async def get_page(page_id: str) -> dict:
    page_id = page_id.strip()
    url = f"{BASE_URL}/pages/{page_id}"
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(url, headers=_get_headers())
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            msg = f"Notion API error (get_page): {e.response.text}"
            print(msg, file=sys.stderr)
            return {"error": msg, "status": e.response.status_code}

@notion_mcp.tool()
async def get_token_info() -> dict:
    url = f"{BASE_URL}/users/me"
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(url, headers=_get_headers())
            response.raise_for_status()
            data = response.json()
            return {
                "bot_name": data.get("bot", {}).get("owner", {}).get("user", {}).get("name", "Unknown"),
                "workspace_name": data.get("bot", {}).get("workspace_name", "Unknown"),
                "type": data.get("type"),
                "can_read": True # If we reached here, we can at least read bot info
            }
        except Exception as e:
            return {"error": str(e)}
