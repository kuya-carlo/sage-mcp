import logging
import os
from contextlib import asynccontextmanager
from typing import Any

import fastmcp
from dotenv import load_dotenv

load_dotenv()

# Silence FastMCP ASCII banner globally
fastmcp.settings.show_server_banner = False

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastmcp.utilities.lifespan import combine_lifespans

from sage.config import settings
from sage.database import db
from sage.services.mcp_tools.server import mcp as mcp_server
from sage.services.notion_mcp import notion_mcp as notion_server

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

# Router imports
from sage.routers import admin, auth, commons
from sage.routers import mcp as mcp_router


@asynccontextmanager
async def lifespan(app: Any):
    logger = logging.getLogger("init")
    try:
        await db.connect(settings.db_url)
        logger.info("SAGE is ready")
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        raise
    yield
    await db.disconnect()


from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware

mcp_app = mcp_server.http_app(
    path="/",
    middleware=[
        Middleware(
            CORSMiddleware,  # ty: ignore[invalid-argument-type]
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )
    ],
)

notion_mcp_app = notion_server.http_app(
    path="/",
    middleware=[
        Middleware(
            CORSMiddleware,  # ty: ignore[invalid-argument-type]
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )
    ],
)

app = FastAPI(
    title=settings.project_name,
    description="Student Agent for Guided Education API",
    lifespan=combine_lifespans(
        lifespan,  # ty: ignore[invalid-argument-type]
        mcp_app.lifespan,
        notion_mcp_app.lifespan,
    ),
    allowed_origins=["*"],
)

# Static directory resolution
static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Include routers
app.include_router(auth.router)
app.include_router(mcp_router.router)
app.include_router(commons.router)
app.include_router(admin.router)


@app.get("/health")
async def health_check():
    return {"status": "ok", "project": settings.project_name}


app.mount("/mcp-server", mcp_app)
app.mount("/notion-native-mcp", notion_mcp_app)


@app.get("/")
async def read_frontend():
    return FileResponse("static/index.html")


if __name__ == "__main__":
    import uvicorn

    # Use reload only in development; default to False for smoother demo videos
    should_reload = os.environ.get("RELOAD", "false").lower() == "true"
    uvicorn.run("sage.main:app", host=settings.host, port=settings.port, reload=should_reload)
