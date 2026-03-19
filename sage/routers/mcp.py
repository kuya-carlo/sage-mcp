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
    if not settings.notion_root_page_id:
        raise HTTPException(
            status_code=500, 
            detail="Settings missing notion_root_page_id required for SAGE workspace operations"
        )
        
    result = await run_agent_loop(
        message=request.message,
        workspace_id=workspace_id,
        workspace_root_id=settings.notion_root_page_id
    )
    
    return result

@router.get("/tools")
async def get_mcp_tools():
    """
    Returns the TOOLS_SCHEMA list from agent.py.
    Used for inspection/debugging without requiring authentication.
    """
    return {"tools": TOOLS_SCHEMA}
