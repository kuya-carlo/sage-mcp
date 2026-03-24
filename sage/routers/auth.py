from fastapi import APIRouter, Response, Request, HTTPException, Depends
from fastapi.responses import RedirectResponse
import httpx
import base64
from cryptography.fernet import Fernet
from sage.config import settings
from sage.database import get_db_pool

router = APIRouter(prefix="/auth", tags=["auth"])

import urllib.parse

@router.get("/notion")
async def notion_login():
    """Redirect to the Notion OAuth authorization URL."""
    params = {
        "client_id": settings.notion_client_id,
        "response_type": "code",
        "owner": "user",
        "redirect_uri": settings.notion_redirect_uri
    }
    encoded_params = urllib.parse.urlencode(params)
    url = f"https://api.notion.com/v1/oauth/authorize?{encoded_params}"
    return RedirectResponse(url=url)

@router.get("/callback")
async def notion_callback(code: str):
    """Handle Notion OAuth callback and exchange code for access token."""
    if not code:
        raise HTTPException(status_code=400, detail="Authorization code is missing")
        
    auth_str = f"{settings.notion_client_id}:{settings.notion_client_secret}"
    b64_auth = base64.b64encode(auth_str.encode()).decode()
    
    headers = {
        "Authorization": f"Basic {b64_auth}",
        "Content-Type": "application/json"
    }
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.notion_redirect_uri
    }
    
    async with httpx.AsyncClient() as client:
        resp = await client.post("https://api.notion.com/v1/oauth/token", headers=headers, json=payload)
        
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=f"Notion OAuth failed: {resp.text}")
        
    data = resp.json()
    access_token = data.get("access_token")
    workspace_id = data.get("workspace_id")
    bot_id = data.get("bot_id", "default_bot")
    
    if not access_token or not workspace_id:
        raise HTTPException(status_code=400, detail="Invalid token response from Notion API")
        
    # Encrypt the access token
    fernet = Fernet(settings.fernet_key.encode())
    encrypted_token = fernet.encrypt(access_token.encode()).decode()
    
    # Store token in database
    pool = await get_db_pool()
    query = """
        INSERT INTO user_tokens (workspace_id, bot_id, encrypted_token)
        VALUES ($1, $2, $3)
        ON CONFLICT (workspace_id)
        DO UPDATE SET encrypted_token = EXCLUDED.encrypted_token, bot_id = EXCLUDED.bot_id
    """
    async with pool.acquire() as connection:
        await connection.execute(query, workspace_id, bot_id, encrypted_token)
        
    # Provide cookie matching current user session
    response = RedirectResponse(url="/static/index.html")
    response.set_cookie(
        key="workspace_id", 
        value=workspace_id, 
        httponly=True,
        samesite="lax"
    )
    return response

async def get_current_user(request: Request) -> str:
    """FastAPI Dependency to get current user workspace_id from cookies."""
    workspace_id = request.cookies.get("workspace_id")
    if not workspace_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    pool = await get_db_pool()
    async with pool.acquire() as connection:
        exists = await connection.fetchval("SELECT 1 FROM user_tokens WHERE workspace_id = $1", workspace_id)
        if not exists:
            raise HTTPException(status_code=401, detail="Token deleted from database")
            
    return workspace_id

@router.get("/status")
async def check_auth_status(request: Request):
    """Allows the frontend to check if the user has an active httponly cookie backed by a real DB row."""
    workspace_id = request.cookies.get("workspace_id")
    if not workspace_id:
        return {"authenticated": False}
        
    pool = await get_db_pool()
    async with pool.acquire() as connection:
        exists = await connection.fetchval("SELECT 1 FROM user_tokens WHERE workspace_id = $1", workspace_id)
        if not exists:
            return {"authenticated": False}
            
    return {"authenticated": True, "workspace_id": workspace_id}

@router.get("/logout")
def logout():
    """Clear session cookie and redirect to onboarding."""
    response = RedirectResponse(url="/static/index.html")
    response.delete_cookie("workspace_id")
    return response
