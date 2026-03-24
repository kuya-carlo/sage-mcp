import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sage.database import db
from sage.config import settings
from sage.services.mcp_tools.server import mcp as mcp_server
from fastmcp.utilities.lifespan import combine_lifespans


import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s"
)

# Router imports
from sage.routers import auth, commons, admin
from sage.routers import mcp as mcp_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger = logging.getLogger("init")
    try:
        await db.connect(settings.supabase_db_url)
        logger.info("SAGE is ready")
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        raise
    yield
    await db.disconnect()

from starlette.middleware.cors import CORSMiddleware
from starlette.middleware import Middleware

mcp_app = mcp_server.http_app(
    path="/",
    middleware=[
        Middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )
    ]
)

app = FastAPI(
    title=settings.project_name,
    description="Student Agent for Guided Education API",
    lifespan=combine_lifespans(lifespan, mcp_app.lifespan),
    allowed_origins=["*"]
)

# Placeholder dynamic static directory resolution
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

app.mount("/mcp-server",mcp_app)
app.mount("/static",StaticFiles(directory="static"), name="static")

@app.get("/")
async def read_frontend():
    return FileResponse("static/index.html")