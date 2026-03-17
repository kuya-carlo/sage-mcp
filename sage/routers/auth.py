from fastapi import APIRouter

router = APIRouter(prefix="/auth", tags=["Notion Authentication"])

@router.get("/login")
async def login():
    return {"message": "Notion Login OAuth stub"}

@router.get("/callback")
async def callback(code: str):
    return {"message": "Notion Callback OAuth stub"}
