import base64
import hashlib
import secrets
from datetime import UTC, datetime, timedelta

import httpx
from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from sage.config import settings
from sage.database import get_db

router = APIRouter(prefix="/auth/notion", tags=["notion-auth"])


async def get_session_id(x_session_id: str = Header(..., alias="X-Session-ID")) -> str:
    """Dependency to get session ID from headers."""
    return x_session_id


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    expires_in: int | None = None


async def discover_oauth_endpoints(resource_url: str):
    """RFC 9470 + RFC 8414 Discovery"""
    async with httpx.AsyncClient() as client:
        # 1. Fetch Protected Resource Metadata (RFC 9470)
        # Note: Resource URL is https://mcp.notion.com/mcp
        # Discovery is at {resource_url}/.well-known/oauth-protected-resource
        discovery_url = f"{resource_url}/.well-known/oauth-protected-resource"
        resp = await client.get(discovery_url)
        resp.raise_for_status()
        resource_metadata = resp.json()

        if not resource_metadata.get("authorization_servers"):
            raise HTTPException(
                status_code=500, detail="No authorization servers found in resource metadata"
            )

        as_url = resource_metadata["authorization_servers"][0]

        # 2. Fetch Authorization Server Metadata (RFC 8414)
        # Suffix is /.well-known/oauth-authorization-server
        as_discovery_url = f"{as_url.rstrip('/')}/.well-known/oauth-authorization-server"
        resp = await client.get(as_discovery_url)
        resp.raise_for_status()
        as_metadata = resp.json()

        return as_metadata["authorization_endpoint"], as_metadata["token_endpoint"]


def generate_pkce_pair():
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest())
        .decode()
        .rstrip("=")
    )
    return code_verifier, code_challenge


@router.get("")
async def auth_notion(request: Request, session_id: str = Query(..., alias="session_id")):
    """
    (1) GET /auth/notion — generate code_verifier, code_challenge, state;
    store verifier+state in Supabase against the user session;
    redirect user to Notion's authorization_endpoint.
    """
    auth_endpoint, _ = await discover_oauth_endpoints("https://mcp.notion.com/mcp")

    code_verifier, code_challenge = generate_pkce_pair()
    state = secrets.token_urlsafe(16)

    # Store in database
    async with get_db() as conn:
        # Table notion_oauth_states: session_id, code_verifier, state, expires_at
        expires_at = datetime.now(UTC) + timedelta(minutes=10)
        await conn.execute(
            """
            INSERT INTO notion_oauth_states (session_id, code_verifier, state, expires_at)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (session_id) DO UPDATE
            SET code_verifier = $2, state = $3, expires_at = $4
            """,
            session_id,
            code_verifier,
            state,
            expires_at,
        )

    params = {
        "client_id": settings.notion_client_id,
        "redirect_uri": settings.notion_redirect_uri,
        "response_type": "code",
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "owner": "user",  # Notion specific
    }

    query_string = "&".join(f"{k}={v}" for k, v in params.items())
    return RedirectResponse(f"{auth_endpoint}?{query_string}")


@router.get("/status")
async def check_notion_status(session_id: str = Query(...)):
    """Check if a session has an active Notion connection."""
    async with get_db() as conn:
        exists = await conn.fetchval("SELECT 1 FROM notion_tokens WHERE user_id = $1", session_id)
        return {"authenticated": bool(exists)}


@router.get("/logout")
async def notion_logout():
    """Clear session data."""
    # We don't really have server-side session yet but we can redirect.
    # The frontend is mostly responsible for clearing localStorage session_id if they want a full clean logout.
    return RedirectResponse(url="/")


@router.get("/callback")
async def auth_notion_callback(
    code: str,
    state: str,
    session_id: str = Query(None),  # Usually passed back or we use state to lookup session
):
    """
    (2) GET /auth/notion/callback — validate state, exchange code for tokens using code_verifier,
    store access_token + refresh_token + expires_at in Supabase notion_tokens table keyed by user ID.
    """
    async with get_db() as conn:
        # We need to find the session_id that matches this state
        record = await conn.fetchrow(
            "SELECT session_id, code_verifier FROM notion_oauth_states WHERE state = $1 AND expires_at > $2",
            state,
            datetime.now(UTC),
        )
        if not record:
            raise HTTPException(status_code=400, detail="Invalid or expired state")

        found_session_id = record["session_id"]
        code_verifier = record["code_verifier"]

        # Cleanup state
        await conn.execute(
            "DELETE FROM notion_oauth_states WHERE session_id = $1", found_session_id
        )

        # Discovery token endpoint
        _, token_endpoint = await discover_oauth_endpoints("https://mcp.notion.com/mcp")

        # Exchange code
        async with httpx.AsyncClient() as client:
            payload = {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.notion_redirect_uri,
                "client_id": settings.notion_client_id,
                "client_secret": settings.notion_client_secret,
                "code_verifier": code_verifier,
            }
            resp = await client.post(token_endpoint, data=payload)
            if resp.is_error:
                raise HTTPException(status_code=400, detail=f"Token exchange failed: {resp.text}")

            token_data = resp.json()
            access_token = token_data["access_token"]
            refresh_token = token_data.get("refresh_token")
            expires_in = token_data.get("expires_in")

            expires_at = None
            if expires_in:
                expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)

            # Use session_id as user_id for now as per instructions "keyed by user session ID stored in localStorage"
            # Actually user said "keyed by user ID" in database, but "user session ID in localStorage" to lookup.
            # We'll assume session_id == user_id for this simple implementation.
            user_id = found_session_id

            await conn.execute(
                """
                INSERT INTO notion_tokens (user_id, access_token, refresh_token, expires_at)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (user_id) DO UPDATE
                SET access_token = $2, refresh_token = $3, expires_at = $4
                """,
                user_id,
                access_token,
                refresh_token,
                expires_at,
            )

    return {
        "status": "success",
        "message": "Notion connected successfully. You can close this tab.",
    }


async def get_notion_token(user_id: str) -> str:
    """
    (3) Add a get_notion_token(user_id) dependency that fetches the token,
    refreshes it if within 5 minutes of expiry using the token_endpoint,
    persists the new token, and returns the fresh access_token.
    """
    async with get_db() as conn:
        record = await conn.fetchrow(
            "SELECT access_token, refresh_token, expires_at FROM notion_tokens WHERE user_id = $1",
            user_id,
        )
        if not record:
            raise HTTPException(status_code=401, detail="Notion not connected")

        access_token = record["access_token"]
        refresh_token = record["refresh_token"]
        expires_at = record["expires_at"]

        # Check if expired or within 5 minutes
        now = datetime.now(UTC)
        if expires_at and (expires_at - now < timedelta(minutes=5)):
            if not refresh_token:
                raise HTTPException(
                    status_code=401, detail="Token expired and no refresh token available"
                )

            # Refresh
            _, token_endpoint = await discover_oauth_endpoints("https://mcp.notion.com/mcp")
            async with httpx.AsyncClient() as client:
                payload = {
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": settings.notion_client_id,
                    "client_secret": settings.notion_client_secret,
                }
                resp = await client.post(token_endpoint, data=payload)
                if resp.is_error:
                    raise HTTPException(status_code=401, detail="Token refresh failed")

                new_token_data = resp.json()
                access_token = new_token_data["access_token"]
                refresh_token = new_token_data.get("refresh_token", refresh_token)
                expires_in = new_token_data.get("expires_in")

                new_expires_at = None
                if expires_in:
                    new_expires_at = now + timedelta(seconds=expires_in)

                await conn.execute(
                    "UPDATE notion_tokens SET access_token = $1, refresh_token = $2, expires_at = $3 WHERE user_id = $4",
                    access_token,
                    refresh_token,
                    new_expires_at,
                    user_id,
                )

        return access_token
