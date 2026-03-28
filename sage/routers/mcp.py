import asyncio

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel

from sage.routers.notion_auth import get_notion_token
from sage.services.agent import TOOLS_SCHEMA, run_agent_loop
from sage.services.notion import NotionService

router = APIRouter(prefix="/mcp", tags=["MCP Server"])


class ChatRequest(BaseModel):
    message: str


async def get_session_id(x_session_id: str = Header(..., alias="X-Session-ID")) -> str:
    return x_session_id


@router.post("/chat")
async def mcp_chat(
    raw_request: Request,
    request: ChatRequest,
    workspace_id: str = Depends(get_session_id),
):
    """
    Accepts a chat message and runs it against the agentic loop.
    If the client disconnects (Stop button), the agent task is cancelled.
    """
    agent_task = asyncio.create_task(
        run_agent_loop(message=request.message, workspace_id=workspace_id)
    )

    # Poll for client disconnect every 0.5 s; cancel the task if detected
    while not agent_task.done():
        if await raw_request.is_disconnected():
            agent_task.cancel()
            return {"response": "⛔ Request cancelled.", "audit_log": []}
        await asyncio.sleep(0.5)

    return agent_task.result()


@router.get("/tools")
async def get_mcp_tools():
    """
    Returns the TOOLS_SCHEMA list from agent.py.
    Used for inspection/debugging without requiring authentication.
    """
    return {"tools": TOOLS_SCHEMA}


@router.get("/load-status")
async def get_load_status(workspace_id: str = Depends(get_session_id)):
    """
    Fetches the current week's weight/burnout score from the Notion Tasks DB.
    """
    from datetime import datetime, timedelta

    from sage.services.mcp_tools.sensor import get_weekly_load

    # Get the Monday of this week for better consistency
    today = datetime.now()
    monday = today - timedelta(days=today.weekday())
    # Use explicitly passed ID, or created root ID
    week_start = monday.strftime("%Y-%m-%d")

    try:
        # Connectivity check: Fetch root page or get users
        access_token = await get_notion_token(workspace_id)
        async with NotionService(access_token=access_token) as notion_service:
            # Verify connection by fetching a simple resource
            try:
                await notion_service._call_mcp("notion-get-users", {})
            except Exception:
                # Fallback to a placeholder if Notion is unreachable
                return {"load_score": 0, "status": "offline"}

            data = await get_weekly_load(workspace_id, week_start, notion_service=notion_service)
            return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
