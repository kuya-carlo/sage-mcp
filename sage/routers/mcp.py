from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from sage.services.agent import TOOLS_SCHEMA, run_agent_loop

router = APIRouter(prefix="/mcp", tags=["MCP Server"])


class ChatRequest(BaseModel):
    message: str


async def get_session_id(x_session_id: str = Header(..., alias="X-Session-ID")) -> str:
    return x_session_id


@router.post("/chat")
async def mcp_chat(request: ChatRequest, workspace_id: str = Depends(get_session_id)):
    """
    Accepts a chat message and runs it against the Claude agentic loop
    with MCP tools exposed.
    """
    result = await run_agent_loop(message=request.message, workspace_id=workspace_id)

    return result


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
    week_start = monday.strftime("%Y-%m-%d")

    try:
        data = await get_weekly_load(workspace_id, week_start)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
