import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sage.database import db
from sage.config import settings

# Router imports
from sage.routers import auth, mcp, commons, admin

@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.connect(settings.supabase_db_url)
    print("SAGE is ready")
    yield
    await db.disconnect()

app = FastAPI(
    title=settings.project_name,
    description="Student Agent for Guided Education API",
    lifespan=lifespan
)

# Placeholder dynamic static directory resolution
static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Include routers
app.include_router(auth.router)
app.include_router(mcp.router)
app.include_router(commons.router)
app.include_router(admin.router)

@app.get("/health")
async def health_check():
    return {"status": "ok", "project": settings.project_name}
