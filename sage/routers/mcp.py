from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sage.config import settings
from sage.routers.auth import get_current_user
from sage.services.agent import run_agent_loop, TOOLS_SCHEMA

router = APIRouter(prefix="/mcp", tags=["MCP Server"])

class ChatRequest(BaseModel):
    message: str

@router.post("/chat")
async def mcp_chat(request: ChatRequest, workspace_id: str = Depends(get_current_user)):
    """
    Accepts a chat message and runs it against the Claude agentic loop
    with MCP tools exposed.
    """
    # Bypassed static workspace_root check to support true multi-user environments
    workspace_root = getattr(settings, "notion_root_page_id", "")
        
    result = await run_agent_loop(
        message=request.message,
        workspace_id=workspace_id
    )
    
    return result

@router.get("/tools")
async def get_mcp_tools():
    """
    Returns the TOOLS_SCHEMA list from agent.py.
    Used for inspection/debugging without requiring authentication.
    """
    return {"tools": TOOLS_SCHEMA}

@router.get("/load-status")
async def get_load_status(workspace_id: str = Depends(get_current_user)):
    """
    Fetches the current week's weight/burnout score from the Notion Tasks DB.
    """
    from sage.services.mcp_tools.sensor import get_weekly_load
    from datetime import datetime, timedelta
    
    # Get the Monday of this week for better consistency
    today = datetime.now()
    monday = today - timedelta(days=today.weekday())
    week_start = monday.strftime("%Y-%m-%d")
    
    try:
        data = await get_weekly_load(workspace_id, week_start)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
