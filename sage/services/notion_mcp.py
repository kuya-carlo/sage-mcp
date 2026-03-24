import httpx
from fastmcp import FastMCP
import os
from typing import Any, Optional

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
    url = f"{BASE_URL}/blocks/{block_id}/children"
    payload = {"children": children}
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.patch(url, headers=_get_headers(), json=payload)
        response.raise_for_status()
        return response.json()

@notion_mcp.tool()
async def search(query: str) -> list:
    url = f"{BASE_URL}/search"
    payload: dict = {
        "filter": {
            "property": "object",
            "value": "page"
        }
    }
    if query:
        payload["query"] = query
        
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, headers=_get_headers(), json=payload)
        response.raise_for_status()
        data = response.json()
        return data.get("results", [])

@notion_mcp.tool()
async def create_page(parent_id: str, title: str, icon_emoji: str = "📚") -> dict:
    url = f"{BASE_URL}/pages"
    payload = {
        "parent": {"page_id": parent_id},
        "properties": {"title": [{"text": {"content": title}}]},
        "icon": {"type": "emoji", "emoji": icon_emoji}
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, headers=_get_headers(), json=payload)
        response.raise_for_status()
        data = response.json()
        return {"id": data["id"], "url": data.get("url", "")}

@notion_mcp.tool()
async def create_database(parent_page_id: str, title: str, properties: dict) -> dict:
    url = f"{BASE_URL}/databases"
    payload = {
        "parent": {"type": "page_id", "page_id": parent_page_id},
        "title": [{"text": {"content": title}}],
        "properties": properties
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, headers=_get_headers(), json=payload)
        response.raise_for_status()
        data = response.json()
        return {"id": data["id"]}

@notion_mcp.tool()
async def create_database_entry(database_id: str, properties: dict) -> dict:
    url = f"{BASE_URL}/pages"
    payload = {
        "parent": {"database_id": database_id},
        "properties": properties
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, headers=_get_headers(), json=payload)
        response.raise_for_status()
        data = response.json()
        return {"id": data["id"]}

@notion_mcp.tool()
async def update_page_property(page_id: str, property_name: str, value: dict) -> dict:
    url = f"{BASE_URL}/pages/{page_id}"
    payload = {"properties": {property_name: value}}
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.patch(url, headers=_get_headers(), json=payload)
        response.raise_for_status()
        data = response.json()
        return {"id": data["id"]}

@notion_mcp.tool()
async def get_database_entries(database_id: str, filter_dict: dict = None) -> list:
    url = f"{BASE_URL}/databases/{database_id}/query"
    payload = {}
    if filter_dict:
        payload["filter"] = filter_dict
    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=_get_headers(), json=payload)
        response.raise_for_status()
        data = response.json()
        return data.get("results", [])

@notion_mcp.tool()
async def get_page(page_id: str) -> dict:
    url = f"{BASE_URL}/pages/{page_id}"
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=_get_headers())
        response.raise_for_status()
        return response.json()
