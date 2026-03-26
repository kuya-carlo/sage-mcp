from fastapi import APIRouter, Depends, Header, HTTPException, BackgroundTasks, UploadFile, File
from pydantic import BaseModel
from sage.config import settings
from sage.database import get_db_pool
from sage.services.etl.seeder import seed_program, upsert_records
from sage.services.etl.local_parser import process_pdf_locally
from sage.services.etl.extractor import chunk_text_blocks, extract_all_chunks

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

@router.post("/upload", dependencies=[Depends(verify_admin)])
async def upload_syllabus(program_code: str, file: UploadFile = File(...)):
    """Manual ETL: Process a local PDF syllabus, extract curriculum, and seed the DB."""
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")
    
    try:
        pdf_bytes = await file.read()
        
        # 1. OCR / Text Extraction (In-house & Free!)
        pages = await process_pdf_locally(pdf_bytes)
        
        # 2. Schema Transformation via Gemini
        chunks = chunk_text_blocks(pages)
        raw_records = await extract_all_chunks(chunks, program_code)
        
        if not raw_records:
            return {"status": "error", "message": "No curriculum records found in PDF."}
        
        # 3. Store in Database
        inserted, failed = await upsert_records(raw_records, program_code)
        
        return {
            "status": "done",
            "program_code": program_code,
            "filename": file.filename,
            "records_inserted": inserted,
            "failed_extractions": failed
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

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
