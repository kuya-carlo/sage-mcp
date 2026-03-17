from fastapi import APIRouter

router = APIRouter(prefix="/commons", tags=["Ghost Commons API"])

@router.get("/tree")
async def get_commons_tree(program_code: str, year_level: int, semester: int):
    return {"message": "Commons tree stub"}
