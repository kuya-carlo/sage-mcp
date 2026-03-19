from fastapi import APIRouter, Response, Request, HTTPException, Depends
from fastapi.responses import RedirectResponse
from sage.config import settings

router = APIRouter(prefix="/auth", tags=["auth"])

@router.get("/notion")
async def notion_login():
    """
    For MVP: redirect directly to / with workspace cookie set.
    Set httponly cookie 'workspace_id' = settings.notion_workspace_id
    Redirect to /static/index.html
    """
    response = RedirectResponse(url="/static/index.html")
    workspace_id = settings.notion_workspace_id
    
    if not workspace_id:
        raise HTTPException(status_code=500, detail="MVP workspace ID not configured in settings")
        
    response.set_cookie(
        key="workspace_id", 
        value=workspace_id, 
        httponly=True,
        samesite="lax"
    )
    return response

@router.get("/callback")
async def notion_callback():
    """
    Placeholder for future OAuth.
    """
    return {"status": "oauth_not_implemented_in_mvp"}

def get_current_user(request: Request) -> str:
    """
    FastAPI Dependency to get current user workspace_id from cookies.
    """
    workspace_id = request.cookies.get("workspace_id")
    if not workspace_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return workspace_id
