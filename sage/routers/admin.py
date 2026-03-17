from fastapi import APIRouter

router = APIRouter(prefix="/admin", tags=["Admin API"])

@router.post("/seed")
async def trigger_seed():
    return {"message": "Admin seed pipeline stub"}
