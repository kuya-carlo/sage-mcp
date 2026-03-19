import httpx
from typing import Dict, Any, List, Optional

class NotionService:
    BASE_URL = "https://api.notion.com/v1"
    VERSION = "2022-06-28"

    @classmethod
    def _get_headers(cls, access_token: str) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {access_token}",
            "Notion-Version": cls.VERSION,
            "Content-Type": "application/json"
        }

    async def create_page(self, access_token: str, parent_id: str, title: str, icon_emoji: str = "📚") -> Dict[str, Any]:
        url = f"{self.BASE_URL}/pages"
        payload = {
            "parent": {"page_id": parent_id},
            "properties": {
                "title": [{"text": {"content": title}}]
            },
            "icon": {"type": "emoji", "emoji": icon_emoji}
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=self._get_headers(access_token), json=payload)
            data = response.json()
            return {"id": data["id"], "url": data["url"]}

    async def create_database(self, access_token: str, parent_page_id: str, title: str, properties: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.BASE_URL}/databases"
        payload = {
            "parent": {"type": "page_id", "page_id": parent_page_id},
            "title": [{"text": {"content": title}}],
            "properties": properties
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=self._get_headers(access_token), json=payload)
            data = response.json()
            return {"id": data["id"]}

    async def create_database_entry(self, access_token: str, database_id: str, properties: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.BASE_URL}/pages"
        payload = {
            "parent": {"database_id": database_id},
            "properties": properties
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=self._get_headers(access_token), json=payload)
            data = response.json()
            return {"id": data["id"]}

    async def update_page_property(self, access_token: str, page_id: str, property_name: str, value: Any) -> Dict[str, Any]:
        url = f"{self.BASE_URL}/pages/{page_id}"
        payload = {
            "properties": {
                property_name: value
            }
        }
        async with httpx.AsyncClient() as client:
            response = await client.patch(url, headers=self._get_headers(access_token), json=payload)
            data = response.json()
            return {"id": data["id"]}

    async def create_calendar_entry(self, access_token: str, calendar_db_id: str, title: str, date: str, protected: bool) -> Dict[str, Any]:
        properties = {
            "Name": {"title": [{"text": {"content": title}}]},
            "Date": {"date": {"start": date}},
            "Protected": {"checkbox": protected}
        }
        return await self.create_database_entry(access_token, calendar_db_id, properties)

    async def get_database_entries(self, access_token: str, database_id: str, filter_dict: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        url = f"{self.BASE_URL}/databases/{database_id}/query"
        payload = {}
        if filter_dict:
            payload["filter"] = filter_dict
            
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=self._get_headers(access_token), json=payload)
            data = response.json()
            return data.get("results", [])

    async def query_tasks_due_this_week(self, access_token: str, database_id: str, week_start: str, week_end: str) -> List[Dict[str, Any]]:
        filter_dict = {
            "and": [
                {"property": "Due Date", "date": {"on_or_after": week_start}},
                {"property": "Due Date", "date": {"on_or_before": week_end}}
            ]
        }
        return await self.get_database_entries(access_token, database_id, filter_dict)

    async def append_block_children(self, access_token: str, page_id: str, children: List[Dict[str, Any]]) -> Dict[str, Any]:
        url = f"{self.BASE_URL}/blocks/{page_id}/children"
        payload = {"children": children}
        async with httpx.AsyncClient() as client:
            response = await client.patch(url, headers=self._get_headers(access_token), json=payload)
            return response.json()

    async def get_page(self, access_token: str, page_id: str) -> Dict[str, Any]:
        url = f"{self.BASE_URL}/pages/{page_id}"
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=self._get_headers(access_token))
            return response.json()

    async def search_pages(self, access_token: str, query: str) -> List[Dict[str, Any]]:
        url = f"{self.BASE_URL}/search"
        payload = {
            "query": query,
            "filter": {
                "property": "object",
                "value": "page"
            }
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=self._get_headers(access_token), json=payload)
            data = response.json()
            return data.get("results", [])
