from fastapi import APIRouter, Depends, Header, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sage.config import settings
from sage.database import get_db_pool
from sage.services.etl.seeder import seed_program

router = APIRouter(prefix="/admin", tags=["Admin API"])

def verify_admin(x_admin_key: str = Header(...)) -> None:
    if not settings.admin_key or x_admin_key != settings.admin_key:
        raise HTTPException(status_code=403, detail="Forbidden: Invalid Admin Key")

class SeedRequest(BaseModel):
    program_code: str

@router.post("/seed", dependencies=[Depends(verify_admin)])
async def trigger_seed(request: SeedRequest, background_tasks: BackgroundTasks):
    background_tasks.add_task(seed_program, request.program_code)
    return {
        "status": "seeding_started",
        "program": request.program_code
    }

@router.get("/seed/status", dependencies=[Depends(verify_admin)])
async def seed_status():
    pool = await get_db_pool()
    
    seeded_query = """
        SELECT program_code, COUNT(*) as record_count
        FROM cmo_records GROUP BY program_code
    """
    failed_query = """
        SELECT program_code, COUNT(*) as failed_count
        FROM failed_extractions GROUP BY program_code
    """
    
    async with pool.acquire() as connection:
        seeded_records = await connection.fetch(seeded_query)
        try:
            failed_records = await connection.fetch(failed_query)
        except Exception:
            # Handle case where failed_extractions table might not exist yet
            failed_records = []
        
    return {
        "seeded": [dict(r) for r in seeded_records],
        "failed": [dict(r) for r in failed_records]
    }

@router.delete("/seed/{program_code}", dependencies=[Depends(verify_admin)])
async def delete_seed(program_code: str):
    pool = await get_db_pool()
    query = "DELETE FROM cmo_records WHERE program_code = $1"
    
    async with pool.acquire() as connection:
        await connection.execute(query, program_code)
        
    return {
        "status": "deleted",
        "program": program_code
    }
