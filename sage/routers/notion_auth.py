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


async def ensure_schema():
    """Ensure necessary columns exist in the database."""
    async with get_db() as conn:
        await conn.execute(
            "ALTER TABLE notion_oauth_states ADD COLUMN IF NOT EXISTS client_id TEXT;"
        )
        await conn.execute(
            "ALTER TABLE notion_oauth_states ADD COLUMN IF NOT EXISTS client_secret TEXT;"
        )
        await conn.execute("ALTER TABLE notion_tokens ADD COLUMN IF NOT EXISTS client_id TEXT;")
        await conn.execute("ALTER TABLE notion_tokens ADD COLUMN IF NOT EXISTS client_secret TEXT;")


async def discover_oauth_endpoints(resource_url: str):
    """RFC 9470 + RFC 8414 Discovery"""
    from urllib.parse import urlparse

    parsed = urlparse(resource_url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    path = parsed.path.strip("/")

    discovery_urls = []
    if path:
        discovery_urls.append(f"{base_url}/.well-known/oauth-protected-resource/{path}")
    discovery_urls.append(f"{base_url}/.well-known/oauth-protected-resource")
    discovery_urls.append(f"{resource_url.rstrip('/')}/.well-known/oauth-protected-resource")

    resource_metadata = None
    async with httpx.AsyncClient() as client:
        for d_url in discovery_urls:
            try:
                resp = await client.get(d_url)
                if resp.status_code == 200:
                    resource_metadata = resp.json()
                    break
            except Exception:
                continue

        if not resource_metadata:
            raise HTTPException(
                status_code=500, detail="Could not discover OAuth Protected Resource Metadata"
            )

        if not resource_metadata.get("authorization_servers"):
            raise HTTPException(
                status_code=500, detail="No authorization servers found in resource metadata"
            )

        as_url = resource_metadata["authorization_servers"][0]

        # 2. Fetch Authorization Server Metadata (RFC 8414)
        as_discovery_url = f"{as_url.rstrip('/')}/.well-known/oauth-authorization-server"
        resp = await client.get(as_discovery_url)
        resp.raise_for_status()
        as_metadata = resp.json()

        return (
            as_metadata["authorization_endpoint"],
            as_metadata["token_endpoint"],
            as_metadata["registration_endpoint"],
        )


async def register_client(registration_endpoint: str) -> tuple[str, str | None]:
    """Perform Dynamic Client Registration (RFC 7591)"""
    payload = {
        "client_name": "SAGE - Student Agent for Guided Education",
        "redirect_uris": [settings.notion_redirect_uri],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(registration_endpoint, json=payload)
        if resp.is_error:
            raise HTTPException(status_code=500, detail=f"Dynamic Registration failed: {resp.text}")
        data = resp.json()
        return data["client_id"], data.get("client_secret")


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
    (1) GET /auth/notion — Dynamically register client, generate PKCE, and redirect.
    """
    await ensure_schema()
    auth_ep, token_ep, reg_ep = await discover_oauth_endpoints("https://mcp.notion.com/mcp")
    client_id, client_secret = await register_client(reg_ep)

    code_verifier, code_challenge = generate_pkce_pair()
    state = secrets.token_urlsafe(16)

    # Store everything in notion_oauth_states
    async with get_db() as conn:
        expires_at = datetime.now(UTC) + timedelta(minutes=10)
        await conn.execute(
            """
            INSERT INTO notion_oauth_states
            (session_id, code_verifier, state, expires_at, client_id, client_secret)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (session_id) DO UPDATE
            SET code_verifier = $2, state = $3, expires_at = $4, client_id = $5, client_secret = $6
            """,
            session_id,
            code_verifier,
            state,
            expires_at,
            client_id,
            client_secret,
        )

    params = {
        "client_id": client_id,
        "redirect_uri": settings.notion_redirect_uri,
        "response_type": "code",
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "owner": "user",
    }

    query_string = "&".join(f"{k}={v}" for k, v in params.items())
    return RedirectResponse(f"{auth_ep}?{query_string}")


@router.get("/status")
async def check_notion_status(session_id: str = Query(...)):
    """Check if a session has an active Notion connection."""
    async with get_db() as conn:
        exists = await conn.fetchval("SELECT 1 FROM notion_tokens WHERE user_id = $1", session_id)
        return {"authenticated": bool(exists)}


@router.get("/logout")
async def notion_logout():
    """Clear session data."""
    return RedirectResponse(url="/")


@router.get("/callback")
async def auth_notion_callback(
    code: str,
    state: str,
    session_id: str = Query(None),
):
    """
    (2) GET /auth/notion/callback — validate state, exchange code, store tokens and client credentials.
    """
    async with get_db() as conn:
        record = await conn.fetchrow(
            """
            SELECT session_id, code_verifier, client_id, client_secret
            FROM notion_oauth_states
            WHERE state = $1 AND expires_at > $2
            """,
            state,
            datetime.now(UTC),
        )
        if not record:
            raise HTTPException(status_code=400, detail="Invalid or expired state")

        found_session_id = record["session_id"]
        code_verifier = record["code_verifier"]
        client_id = record["client_id"]
        client_secret = record["client_secret"]

        # Cleanup state
        await conn.execute(
            "DELETE FROM notion_oauth_states WHERE session_id = $1", found_session_id
        )

        _, token_endpoint, _ = await discover_oauth_endpoints("https://mcp.notion.com/mcp")

        # Exchange code
        async with httpx.AsyncClient() as client:
            payload = {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.notion_redirect_uri,
                "client_id": client_id,
                "code_verifier": code_verifier,
            }
            if client_secret:
                payload["client_secret"] = client_secret

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

            user_id = found_session_id
            await conn.execute(
                """
                INSERT INTO notion_tokens (user_id, access_token, refresh_token, expires_at, client_id, client_secret)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (user_id) DO UPDATE
                SET access_token = $2, refresh_token = $3, expires_at = $4, client_id = $5, client_secret = $6
                """,
                user_id,
                access_token,
                refresh_token,
                expires_at,
                client_id,
                client_secret,
            )

    return {
        "status": "success",
        "message": "Notion connected successfully. You can close this tab.",
    }


async def get_notion_token(user_id: str) -> str:
    """
    (3) Fetch token, refresh using stored client credentials if needed.
    """
    async with get_db() as conn:
        record = await conn.fetchrow(
            """
            SELECT access_token, refresh_token, expires_at, client_id, client_secret
            FROM notion_tokens
            WHERE user_id = $1
            """,
            user_id,
        )
        if not record:
            raise HTTPException(status_code=401, detail="Notion not connected")

        access_token = record["access_token"]
        refresh_token = record["refresh_token"]
        expires_at = record["expires_at"]
        client_id = record["client_id"]
        client_secret = record["client_secret"]

        now = datetime.now(UTC)
        if expires_at and (expires_at - now < timedelta(minutes=5)):
            if not refresh_token:
                raise HTTPException(
                    status_code=401, detail="Token expired and no refresh token available"
                )

            _, token_endpoint, _ = await discover_oauth_endpoints("https://mcp.notion.com/mcp")
            async with httpx.AsyncClient() as client:
                payload = {
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": client_id,
                }
                if client_secret:
                    payload["client_secret"] = client_secret

                resp = await client.post(token_endpoint, data=payload)
                if resp.is_error:
                    raise HTTPException(status_code=401, detail="Token refresh failed")

                new_data = resp.json()
                access_token = new_data["access_token"]
                refresh_token = new_data.get("refresh_token", refresh_token)
                expires_in = new_data.get("expires_in")

                new_expires_at = None
                if expires_in:
                    new_expires_at = now + timedelta(seconds=expires_in)

                await conn.execute(
                    """
                    UPDATE notion_tokens
                    SET access_token = $1, refresh_token = $2, expires_at = $3
                    WHERE user_id = $4
                    """,
                    access_token,
                    refresh_token,
                    new_expires_at,
                    user_id,
                )

        return access_token
