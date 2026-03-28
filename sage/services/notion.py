import json
import logging
import re
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
        self._tools_listed = False
        self._client: httpx.AsyncClient | None = None
        self._streams: Any | None = None
        self._session: ClientSession | None = None

    async def __aenter__(self):
        headers = {"Authorization": f"Bearer {self.access_token}"}
        self._client = httpx.AsyncClient(headers=headers)
        self._streams_cm = streamable_http_client(self.url, http_client=self._client)
        self._streams = await self._streams_cm.__aenter__()
        read_stream, write_stream, _ = self._streams
        self._session = ClientSession(read_stream, write_stream)
        await self._session.__aenter__()
        await self._session.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._session:
            await self._session.__aexit__(exc_type, exc_val, exc_tb)
        if self._streams_cm:
            await self._streams_cm.__aexit__(exc_type, exc_val, exc_tb)
        if self._client:
            await self._client.aclose()
        self._session = None
        self._streams = None
        self._client = None

    async def list_tools(self) -> list[dict[str, Any]]:
        """Utility method to log all available tools on the Notion MCP server."""
        if self._session:
            result = await self._session.list_tools()
            return self._parse_tools(result)

        headers = {"Authorization": f"Bearer {self.access_token}"}
        try:
            async with httpx.AsyncClient(headers=headers) as client:
                async with streamable_http_client(self.url, http_client=client) as streams:
                    read_stream, write_stream, _ = streams
                    async with ClientSession(read_stream, write_stream) as session:
                        await session.initialize()
                        result = await session.list_tools()
                        return self._parse_tools(result)
        except Exception as e:
            logger.error(f"Failed to list tools: {e}")
            return []

    def _parse_tools(self, result: Any) -> list[dict[str, Any]]:
        tools_info = []
        for tool in result.tools:
            tools_info.append(
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.inputSchema,
                }
            )
        logger.info("🧩 Detailed Notion MCP tools info:")
        for info in tools_info:
            logger.info(f"  - {info['name']}: {info['description'][:100]}...")
        return tools_info

    async def _call_mcp(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """
        Calls a tool on the official Notion MCP server using the Streamable HTTP transport.
        """
        logs = audit_logs.get() or []
        logs.append(f"🧩 {tool_name}")
        audit_logs.set(logs)

        # Use cached session if available
        if self._session:
            try:
                result = await self._session.call_tool(tool_name, arguments)
                return self._parse_tool_result(tool_name, arguments, result)
            except Exception as e:
                logger.error(f"❌ MCP {tool_name}: SESSION ERROR - {e}")
                return {"error": str(e)}

        headers = {"Authorization": f"Bearer {self.access_token}"}
        try:
            async with httpx.AsyncClient(headers=headers) as client:
                async with streamable_http_client(self.url, http_client=client) as streams:
                    read_stream, write_stream, _ = streams
                    async with ClientSession(read_stream, write_stream) as session:
                        await session.initialize()
                        result = await session.call_tool(tool_name, arguments)
                        return self._parse_tool_result(tool_name, arguments, result)
        except Exception as e:
            logger.error(
                f"❌ MCP {tool_name}: TRANSPORT ERROR - {e} | Payload: {json.dumps(arguments)}"
            )
            return {"error": str(e)}

    def _parse_tool_result(self, tool_name: str, arguments: dict[str, Any], result: Any) -> Any:
        if result.isError:
            err_msg = str(result.content)
            logger.error(
                f"❌ MCP {tool_name}: FAILED - {err_msg} | Payload: {json.dumps(arguments)}"
            )
            return {"error": err_msg}

        logger.info(f"✅ MCP {tool_name}: SUCCESS")
        if result.content and len(result.content) > 0:
            content = result.content[0]
            text_content = getattr(content, "text", None)
            if isinstance(text_content, str | bytes | bytearray):
                try:
                    return json.loads(text_content)
                except json.JSONDecodeError:
                    return text_content
        return {}

    def _extract_page_id(self, markdown_text: str) -> str | None:
        """
        Extracts the page UUID from the Notion Markdown text returned by
        notion-create-pages / notion-create-database.
        Looks for a notion.so URL like:
          https://www.notion.so/Page-Title-<uuid_nodashes>
        or a bare UUID in the text.
        """
        # Match a 32-char hex UUID (with or without dashes) from a notion.so URL
        url_match = re.search(
            r"notion\.so/\S*?([0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12})",
            markdown_text,
            re.IGNORECASE,
        )
        if url_match:
            raw_id = url_match.group(1)
            # Normalise to dashed UUID format
            if "-" not in raw_id and len(raw_id) == 32:
                raw_id = (
                    f"{raw_id[:8]}-{raw_id[8:12]}-{raw_id[12:16]}-{raw_id[16:20]}-{raw_id[20:]}"
                )
            return raw_id
        # Fallback: any bare UUID-shaped string in the text
        bare_match = re.search(
            r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
            markdown_text,
            re.IGNORECASE,
        )
        if bare_match:
            return bare_match.group(1)
        return None

    def _flatten_properties(self, properties: dict[str, Any]) -> dict[str, Any]:
        """Flattens complex Notion property objects into simple values for the SQL-like MCP."""
        flat = {}
        for k, v in properties.items():
            if isinstance(v, dict):
                if "title" in v:
                    title_val = v["title"]
                    if isinstance(title_val, list) and title_val:
                        flat[k] = (
                            title_val[0].get("text", {}).get("content", "")
                            if isinstance(title_val[0], dict)
                            else str(title_val[0])
                        )
                    else:
                        flat[k] = str(title_val)
                elif "select" in v:
                    flat[k] = v["select"].get("name", "")
                elif "date" in v:
                    flat[k] = v["date"].get("start", "")
                elif "checkbox" in v:
                    flat[k] = 1 if v["checkbox"] else 0
                elif "number" in v:
                    flat[k] = v["number"]
                elif "rich_text" in v:
                    rt = v["rich_text"]
                    if isinstance(rt, list):
                        flat[k] = "".join(
                            p.get("text", {}).get("content", "") for p in rt if isinstance(p, dict)
                        )
                    else:
                        flat[k] = str(rt)
                else:
                    flat[k] = str(v)
            else:
                flat[k] = v
        return flat

    async def create_root_page(self, title: str) -> dict[str, Any]:
        """Creates a page at the workspace level (no parent)."""
        result = await self._call_mcp(
            "notion-create-pages",
            {
                "pages": [{"properties": {"title": title}, "icon": "🎓"}],
            },
        )
        return self._wrap_page_result(result)

    async def create_page(
        self, parent_id: str, title: str, icon_emoji: str = "📚"
    ) -> dict[str, Any]:
        result = await self._call_mcp(
            "notion-create-pages",
            {
                "pages": [
                    {
                        "properties": {"title": title},
                        "icon": icon_emoji,
                    }
                ],
                "parent": {"type": "page_id", "page_id": parent_id},
            },
        )
        return self._wrap_page_result(result)

    def _wrap_page_result(self, result: Any) -> dict[str, Any]:
        """
        Normalise the response from notion-create-pages / notion-create-database
        into {"id": "<uuid>", ...} or {"error": "<msg>"}.

        Observed response shapes:
          * {"pages": [{"id": "...", "url": "...", "properties": {...}}]}  <- notion-create-pages
          * {"id": "...", ...}                                              <- bare page object
          * "Markdown text with notion.so/... URL"                         <- text response
          * {"error": "..."}                                               <- already an error
        """
        if not isinstance(result, dict):
            # Handle list-of-pages
            if isinstance(result, list) and result:
                first = result[0]
                if isinstance(first, dict) and "id" in first:
                    return first
                result = str(first)

            # Text/Markdown response — try to parse out a UUID
            if isinstance(result, str):
                if not result.strip():
                    return {"error": "Empty response from Notion MCP server"}
                page_id = self._extract_page_id(result)
                if page_id:
                    logger.info(f"Parsed page/db ID from Markdown response: {page_id}")
                    return {"id": page_id, "raw": result}
                logger.error(f"Could not extract page ID from MCP response: {result[:200]}")
                return {"error": f"Could not parse page ID from response: {result[:200]}"}

            return {"error": f"Unrecognised MCP response type {type(result)}: {result}"}

        # It's a dict — check for error first
        if "error" in result:
            return result

        # Direct page/database object: {"id": "...", ...}
        if "id" in result:
            return result

        # notion-create-pages wraps as {"pages": [{"id": ..., "url": ..., ...}]}
        if "pages" in result and isinstance(result["pages"], list) and result["pages"]:
            first = result["pages"][0]
            if isinstance(first, dict) and "id" in first:
                logger.info(f"Unwrapped page from pages[]: id={first['id']}")
                return first

        logger.error(f"_wrap_page_result: unrecognised dict shape: {result}")
        return {"error": f"Unexpected dict response (no id): {result}"}

    def _wrap_db_result(self, result: Any) -> dict[str, Any]:
        """
        Unwrap a notion-create-database response.

        Actual response: {'result': 'Created database: <database url="{{https://www.notion.so/UUID}}"...'}
        Also handles {'databases': [...]} in case of server version differences.
        Falls back to _wrap_page_result for any other shape.
        """
        if isinstance(result, dict):
            if "error" in result:
                return result
            # Actual shape: {'result': 'Created database: <database url="{{https://...UUID...}}"...'}
            if "result" in result and isinstance(result["result"], str):
                db_id = self._extract_page_id(result["result"])
                if db_id:
                    logger.info(f"Unwrapped db from result string: id={db_id}")
                    return {"id": db_id, "raw": result["result"]}
            # Alternate shape: {'databases': [{...}]}
            if (
                "databases" in result
                and isinstance(result["databases"], list)
                and result["databases"]
            ):
                first = result["databases"][0]
                if isinstance(first, dict):
                    db_id = first.get("id") or self._extract_page_id(first.get("url", ""))
                    if db_id:
                        logger.info(f"Unwrapped db from databases[]: id={db_id}")
                        return {"id": db_id, **first}
        # Some server versions may return databases wrapped as pages
        return self._wrap_page_result(result)

    async def create_database(
        self, parent_page_id: str, title: str, properties: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Convert properties dict to a Notion DDL CREATE TABLE statement.

        Notion DDL types (NOT SQL types):
          title      → the primary title column (first, required)
          text       → plain rich text
          select     → single-option dropdown (options: ('val1', 'val2'))
          multi_select → multi-option dropdown
          date       → date picker
          checkbox   → boolean toggle
          number     → numeric
          url        → URL field
        """
        title_cols: list[str] = []
        other_cols: list[str] = []

        for col_name, col_def in properties.items():
            if "title" in col_def:
                # title must be first and uses the `title` type keyword
                title_cols.append(f'"{col_name}" title')
            elif "select" in col_def:
                # Notion DDL requires options to be declared in the CREATE TABLE statement
                options = col_def["select"].get("options", [])
                if options:
                    quoted_opts = ", ".join(f"'{o['name']}'" for o in options if "name" in o)
                    other_cols.append(f'"{col_name}" select ({quoted_opts})')
                else:
                    other_cols.append(f'"{col_name}" select')
            elif "multi_select" in col_def:
                options = col_def["multi_select"].get("options", [])
                if options:
                    quoted_opts = ", ".join(f"'{o['name']}'" for o in options if "name" in o)
                    other_cols.append(f'"{col_name}" multi_select ({quoted_opts})')
                else:
                    other_cols.append(f'"{col_name}" multi_select')
            elif "date" in col_def:
                other_cols.append(f'"{col_name}" date')
            elif "checkbox" in col_def:
                other_cols.append(f'"{col_name}" checkbox')
            elif "number" in col_def:
                other_cols.append(f'"{col_name}" number')
            elif "url" in col_def:
                other_cols.append(f'"{col_name}" url')
            else:
                other_cols.append(f'"{col_name}" text')

        all_cols = title_cols + other_cols
        ddl = f'CREATE TABLE "{title}" ({", ".join(all_cols)});'
        logger.info(f"create_database DDL: {ddl}")
        result = await self._call_mcp(
            "notion-create-database",
            {
                "schema": ddl,
                "parent": {"type": "page_id", "page_id": parent_page_id},
                "title": title,
            },
        )
        logger.info(f"create_database raw result: {result}")
        return self._wrap_db_result(result)

    async def create_database_entry(
        self, database_id: str, properties: dict[str, Any]
    ) -> dict[str, Any]:
        result = await self._call_mcp(
            "notion-create-pages",
            {
                "pages": [{"properties": self._flatten_properties(properties)}],
                "parent": {"type": "database_id", "database_id": database_id},
            },
        )
        return self._wrap_page_result(result)

    async def create_pages(
        self, parent_id: str, parent_type: str, pages_data: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """
        Batch create multiple pages/entries under a single parent.
        `pages_data` should be a list of dicts with 'properties' and optionally 'children', 'icon', etc.
        """
        flattened_pages = []
        for p in pages_data:
            new_p = p.copy()
            if "properties" in new_p:
                new_p["properties"] = self._flatten_properties(new_p["properties"])
            flattened_pages.append(new_p)

        result = await self._call_mcp(
            "notion-create-pages",
            {
                "pages": flattened_pages,
                "parent": {"type": parent_type, parent_type: parent_id},
            },
        )
        # Wrap result: handle list of pages or the {"pages": [...]} wrapper
        if isinstance(result, dict) and "pages" in result and isinstance(result["pages"], list):
            return result["pages"]
        if isinstance(result, list):
            return result
        # Fallback to wrap_page_result logic if it's a single page or error
        wrapped = self._wrap_page_result(result)
        return [wrapped] if "id" in wrapped else [result]

    def _parse_resource_xml(self, xml_text: str) -> list[dict[str, Any]]:
        """Parses the XML-like markup from notion-fetch or notion-search into a list of objects."""
        resources = []
        # Match <page ...> or <database ...>
        # We look for the properties JSON first as it usually contains the title
        matches = re.finditer(r"<(page|database).*?>(.*?)<\/\1>", xml_text, re.DOTALL)
        for match in matches:
            tag_type = match.group(1)
            inner_content = match.group(2)

            res = {"type": tag_type}

            # Extract ID from URL in the opening tag if possible
            # <page url="https://www.notion.so/Page-Title-uuid" ...>
            url_match = re.search(r'url="(.*?)"', match.group(0))
            if url_match:
                res["url"] = url_match.group(1)
                page_id = self._extract_page_id(res["url"])
                if page_id:
                    res["id"] = page_id

            # Extract properties JSON
            prop_match = re.search(r"<properties>(.*?)</properties>", inner_content, re.DOTALL)
            if prop_match:
                try:
                    res["properties"] = json.loads(prop_match.group(1).strip())
                    # Normalise title for easier access
                    title_obj = res["properties"].get("title") or res["properties"].get("Name")
                    if isinstance(title_obj, str):
                        res["title"] = title_obj
                    elif isinstance(title_obj, dict):
                        # Handle structured title if needed
                        pass
                except json.JSONDecodeError:
                    pass

            resources.append(res)

        return resources

    async def update_page_property(
        self, page_id: str, property_name: str, value: Any
    ) -> dict[str, Any]:
        """Updates a page property using the notion-update-page tool."""
        # Value should be a dict like {"checkbox": True} or {"select": {"name": "..."}}
        # But the MCP command might expect a simplified format or the SQL-like format
        # Based on notion-update-page description: "Update a Notion page's properties or content"
        return await self._call_mcp(
            "notion-update-page",
            {
                "page_id": page_id,
                "properties": {property_name: value},
                "command": "update_properties",
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
        raise NotImplementedError(
            "get_database_entries is no longer available in the official server list."
        )

    async def query_tasks_due_this_week(
        self, database_id: str, week_start: str, week_end: str
    ) -> list[dict[str, Any]]:
        """
        Queries a database for entries with a date property between week_start and week_end.
        Since the Notion MCP server lacks a direct query tool, we fetch the DB and parse the XML content.
        """
        # 1. Fetch the entire database content
        res = await self._call_mcp("notion-fetch", {"id": database_id})
        if "error" in res:
            logger.error(f"Failed to fetch database {database_id} for querying: {res['error']}")
            return []

        text_content = res.get("text", "") if isinstance(res, dict) else str(res)
        if not text_content:
            return []

        # 2. Extract all <properties> JSON blocks within entries
        entries = []
        matches = re.finditer(r"<properties>(.*?)</properties>", text_content, re.DOTALL)

        for match in matches:
            try:
                props_json = match.group(1).strip()
                props = json.loads(props_json)

                is_match = False
                for p_name, p_val in props.items():
                    if p_name.lower() in ["due date", "date"]:
                        date_str = ""
                        if isinstance(p_val, str):
                            date_str = p_val
                        elif isinstance(p_val, dict) and "start" in p_val:
                            date_str = p_val["start"]

                        if date_str and week_start <= date_str <= week_end:
                            is_match = True
                            break

                if is_match:
                    entries.append(props)
            except (json.JSONDecodeError, KeyError):
                continue

        logger.info(
            f"Query DB {database_id}: Found {len(entries)} tasks between {week_start} and {week_end}"
        )
        return entries

    async def append_block_children(
        self, page_id: str, children: list[dict[str, Any]]
    ) -> dict[str, Any]:
        # Convert block objects to Notion Markdown
        lines = []
        for block in children:
            btype = block.get("type", "")
            if btype == "heading_2":
                text = block["heading_2"]["rich_text"][0]["text"]["content"]
                lines.append(f"## {text}")
            elif btype == "paragraph":
                text = block["paragraph"]["rich_text"][0]["text"]["content"]
                lines.append(text)
            elif btype == "callout":
                text = block["callout"]["rich_text"][0]["text"]["content"]
                lines.append(f"> {text}")
        content = "\n\n".join(lines)
        return await self._call_mcp(
            "notion-update-page",
            {
                "page_id": page_id,
                "command": "replace_content",
                "new_str": content,
            },
        )

    async def get_page(self, page_id: str) -> dict[str, Any]:
        res = await self._call_mcp("notion-fetch", {"id": page_id})
        if isinstance(res, dict) and "text" in res:
            parsed = self._parse_resource_xml(res["text"])
            if parsed:
                return parsed[0]
        return self._wrap_page_result(res)

    async def search_pages(self, query: str = "") -> list[dict[str, Any]]:
        if not query or not query.strip():
            raise ValueError("search_pages requires a non-empty query")
        res = await self._call_mcp("notion-search", {"query": query, "filters": {}})
        if isinstance(res, dict) and "text" in res:
            return self._parse_resource_xml(res["text"])
        return res if isinstance(res, list) else []

    async def search_databases(self, query: str = "") -> list[dict[str, Any]]:
        effective_query = query if query.strip() else " "
        res = await self._call_mcp("notion-search", {"query": effective_query, "filters": {}})
        if isinstance(res, dict) and "text" in res:
            # Filters are not supported in notion-search but we can filter the parsed results
            all_res = self._parse_resource_xml(res["text"])
            return [r for r in all_res if r.get("type") == "database"]
        return res if isinstance(res, list) else []
