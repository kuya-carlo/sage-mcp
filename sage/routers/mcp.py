from fastapi import APIRouter

router = APIRouter(prefix="/mcp", tags=["Model Context Protocol Server"])

@router.post("/")
async def mcp_endpoint():
    return {"message": "MCP POST stub"}
