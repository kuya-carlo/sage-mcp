from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List
from sage.database import get_db_pool
from sage.routers.auth import get_current_user
from sage.models.cmo import CMORecord

router = APIRouter(prefix="/commons", tags=["Ghost Commons API"])

@router.get("/programs")
async def get_programs():
    """Returns a list of all distinct program codes."""
    pool = await get_db_pool()
    query = "SELECT DISTINCT program_code FROM programs ORDER BY program_code"
    
    async with pool.acquire() as connection:
        records = await connection.fetch(query)
        
    return {"programs": [record["program_code"] for record in records]}

@router.get("/tree", response_model=List[CMORecord])
async def get_commons_tree(
    program_code: str, 
    year_level: int, 
    semester: int,
    workspace_id: str = Depends(get_current_user)
):
    """Returns the CMO records for a specific program, year, and semester."""
    pool = await get_db_pool()
    query = """
        SELECT * FROM cmo_records 
        WHERE program_code = $1 AND year_level = $2 AND semester = $3
    """
    
    async with pool.acquire() as connection:
        records = await connection.fetch(query, program_code, year_level, semester)
        
    if not records:
        raise HTTPException(status_code=404, detail="No records found for the given criteria.")
        
    return [dict(record) for record in records]

@router.get("/search", response_model=List[CMORecord])
async def search_commons(
    q: str = Query(..., description="Search query"),
    workspace_id: str = Depends(get_current_user)
):
    """Searches courses by title or competency tag."""
    pool = await get_db_pool()
    query = """
        SELECT * FROM cmo_records 
        WHERE course_title ILIKE $1 OR $2 = ANY(competency_tags)
        LIMIT 20
    """
    
    # We use ILIKE '%{q}%' for the title, but exact match for the array element
    search_term = f"%{q}%"
    
    async with pool.acquire() as connection:
        records = await connection.fetch(query, search_term, q)
        
    return [dict(record) for record in records]
