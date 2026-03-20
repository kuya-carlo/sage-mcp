import asyncio
from sage.database import get_db_pool
from sage.services.etl.seeder import seed_program

async def get_commons_tree(program_code: str, year_level: int, semester: int) -> dict:
    """
    Implements the get_commons_tree MCP tool.
    Retrieves curriculum records. If no records are found, it triggers a background
    seeding task and returns a 'seeding_in_progress' status.
    
    When seeding_status is "seeding_in_progress", the agent should inform the user
    to retry in 30-60 seconds.
    """
    program_code = program_code.upper()
    print(f"[commons] Querying: program={program_code} year={year_level} sem={semester}")
    pool = await get_db_pool()
    query = """
        SELECT * FROM cmo_records
        WHERE program_code = $1 AND year_level = $2 AND semester = $3
        ORDER BY course_code
    """
    
    async with pool.acquire() as connection:
        rows = await connection.fetch(query, program_code, year_level, semester)
        
    if rows:
        return {
            "program_code": program_code,
            "year_level": year_level,
            "semester": semester,
            "courses": [
                {
                    "course_code": row["course_code"],
                    "course_title": row["course_title"],
                    "competency_tags": row["competency_tags"],
                    "cmo_reference": row["cmo_reference"]
                }
                for row in rows
            ],
            "total_courses": len(rows),
            "seeding_status": "ready"
        }
    else:
        # Trigger background seeding process
        asyncio.create_task(seed_program(program_code))
        
        return {
            "program_code": program_code,
            "year_level": year_level,
            "semester": semester,
            "courses": [],
            "total_courses": 0,
            "seeding_status": "seeding_in_progress"
        }

async def programs() -> list:
    """
    Implements the programs MCP tool.
    Retrieves all program codes and names from the database.
    """
    pool = await get_db_pool()
    query = "SELECT DISTINCT program_code, program_name FROM programs ORDER BY program_code"
    async with pool.acquire() as connection:
        rows = await connection.fetch(query)
    return [{"code": record["program_code"], "name": record["program_name"]} for record in rows]